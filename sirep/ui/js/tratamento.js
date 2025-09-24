(function (global) {
  'use strict';

  const { formatDateBR, normalizeText, downloadBlob, api, attachCopyHandlers } = global.SirepUtils;
  const { elements: el } = global.SirepDOM;
  const Logs = global.SirepLogs;

  const state = {
    timer: null,
    dados: null,
    loading: false,
    tablePage: 1,
    searchTerm: '',
    queueView: 'queue',
  };

  const TREATMENT_TABLE_PAGE_SIZE = 10;

  function formatCnpjDisplay(cnpjs, options = {}) {
    const { enableCopy = true, prefer } = options;
    const entries = [];

    const escapeAttr = (value) =>
      String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/"/g, '&quot;');

    const escapeHtml = (value) =>
      String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');


    const formatCnpjDigits = (digits) => {
      const clean = String(digits || '').replace(/\D+/g, '');
      if (clean.length !== 14) {
        return null;
      }
      return `${clean.slice(0, 2)}.${clean.slice(2, 5)}.${clean.slice(5, 8)}/${clean.slice(8, 12)}-${clean.slice(12)}`;
    };

    const extractCnpjCandidates = (value) => {
      const rawValue = String(value ?? '').trim();
      if (!rawValue) {
        return [];
      }

      const normalized = rawValue.replace(/\r\n/g, ' ').replace(/\s+/g, ' ');
      const formattedMatches = [];
      const formattedPattern = /\d{2}(?:\.\d{3}){2}\/\d{4}-\d{2}/g;
      let formattedMatch;
      while ((formattedMatch = formattedPattern.exec(normalized)) !== null) {
        formattedMatches.push(formattedMatch[0]);
      }

      const compactMatches = [];
      const compactPattern = /\d{14}/g;
      let compactMatch;
      while ((compactMatch = compactPattern.exec(normalized)) !== null) {
        const formatted = formatCnpjDigits(compactMatch[0]);
        if (formatted) {
          compactMatches.push(formatted);
        }
      }

      const combined = [...formattedMatches, ...compactMatches];
      if (combined.length) {
        const seen = new Set();
        const results = [];
        combined.forEach((candidate) => {
          const digits = candidate.replace(/\D+/g, '');
          if (digits.length !== 14 || seen.has(digits)) {
            return;
          }
          seen.add(digits);
          const formatted = formatCnpjDigits(digits) || candidate;
          results.push(formatted);
        });
        if (results.length) {
          return results;
        }
      }

      const fallbackFormatted = formatCnpjDigits(rawValue);
      if (fallbackFormatted) {
        return [fallbackFormatted];
      }
      return [];
    };

    const addEntry = (value) => {
      const candidates = extractCnpjCandidates(value);
      if (!candidates.length) {
        return null;
      }

      let firstEntry = null;
      candidates.forEach((candidate) => {
        const digits = candidate.replace(/\D+/g, '');
        if (!digits) {
          return;
        }
        let entry = entries.find((item) => item.digits === digits);
        if (!entry) {
          entry = { raw: candidate, digits };
          entries.push(entry);
        }
        if (!firstEntry) {
          firstEntry = entry;
        }
      });

      return firstEntry;

    const addEntry = (value) => {
      const raw = String(value ?? '').trim();
      if (!raw) {
        return null;
      }
      const digits = raw.replace(/\D+/g, '');
      if (!digits) {
        return null;
      }
      const existing = entries.find((entry) => entry.digits === digits);
      if (existing) {
        return existing;
      }
      const entry = { raw, digits };
      entries.push(entry);
      return entry;

    };

    if (Array.isArray(cnpjs)) {
      cnpjs.forEach((value) => {
        addEntry(value);
      });
    }

    let primary = null;
    const preferStr = typeof prefer === 'string' ? prefer.trim() : '';
    if (preferStr) {
      primary = addEntry(preferStr);
    }

    if (!primary && entries.length) {
      [primary] = entries;
    }

    if (!primary) {
      return '—';
    }

    const primaryIndex = entries.indexOf(primary);
    if (primaryIndex > 0) {
      entries.splice(primaryIndex, 1);
      entries.unshift(primary);
    }

    const extras = entries.slice(1);

    const renderPrimary = () => {
      if (!enableCopy) {
        return escapeHtml(primary.raw);
      }
      const copyValue = escapeAttr(primary.raw);
      const label = escapeHtml(primary.raw);
      return `<a class="copy" data-copy="${copyValue}" data-copy-type="cnpj" href="#">${label}</a>`;
    };

    if (!extras.length) {
      return renderPrimary();
    }


    }

    const extras = entries.slice(1);

    const renderPrimary = () => {
      if (!enableCopy) {
        return escapeHtml(primary.raw);
      }
      const copyValue = escapeAttr(primary.raw);
      const label = escapeHtml(primary.raw);
      return `<a class="copy" data-copy="${copyValue}" data-copy-type="cnpj" href="#">${label}</a>`;
    };

    if (!extras.length) {
      return renderPrimary();
    }

    const tooltipValues = entries.map((entry) => entry.raw);
    const tooltip = escapeAttr(tooltipValues.join(' • '));

    return `
      <span class="cnpj-cell" title="${tooltip}">
        ${renderPrimary()}<span class="muted" aria-hidden="true"> (+${extras.length})</span>
        <span class="sr-only">, mais ${extras.length} CNPJ(s) oculto(s)</span>
      </span>
    `.trim();
  }

  function formatCount(value) {
    const numeric = Number(value ?? 0);
    if (!Number.isFinite(numeric) || numeric < 0) {
      return '0';
    }
    return numeric.toLocaleString('pt-BR');
  }

  function setTratamentoEstado(estado) {
    if (!el.tratamentoEstado || !el.btnTratamentoIniciar || !el.btnTratamentoPausar || !el.btnTratamentoContinuar) {
      return;
    }

    const status = String(estado || '');
    let label = 'Ocioso';
    if (status === 'processando') label = 'Em execução';
    else if (status === 'aguardando') label = 'Aguardando fila';
    else if (status === 'pausado') label = 'Pausado';
    el.tratamentoEstado.textContent = label;

    el.btnTratamentoIniciar.disabled = !(status === 'ocioso' || status === 'aguardando');
    el.btnTratamentoPausar.disabled = status !== 'processando';
    const canContinue = status === 'pausado';
    el.btnTratamentoContinuar.disabled = !canContinue;
    el.btnTratamentoContinuar.classList.toggle('primary', canContinue);
  }

  function formatTreatmentStatus(status) {
    const map = {
      pendente: 'Pendente',
      processando: 'Processando',
      rescindido: 'Rescindido',
      descartado: 'Descartado',
    };
    const key = String(status || '').toLowerCase();
    return map[key] || status || '';
  }

  function renderTratamentoFila(data) {
    if (!el.tbodyTratamentoFila) {
      return;
    }

    el.tbodyTratamentoFila.innerHTML = '';
    const planos = Array.isArray(data.planos) ? data.planos : [];
    let atual = null;
    const atualId = typeof data.atual === 'number' ? data.atual : null;
    if (atualId != null) {
      atual = planos.find((item) => item.id === atualId) || null;
    }
    if (!atual) {
      atual = planos.find((item) => (item.status || '').toLowerCase() === 'processando') || null;
    }

    if (!atual) {
      if (el.tratamentoEmpty) {
        el.tratamentoEmpty.hidden = false;
      }
      return;
    }

    if (el.tratamentoEmpty) {
      el.tratamentoEmpty.hidden = true;
    }

    const tr = document.createElement('tr');
    tr.classList.add('queue-row');
    const statusKey = (atual.status || '').toLowerCase();
    if (statusKey === 'processando') tr.classList.add('current');
    if (statusKey === 'rescindido') tr.classList.add('rescindido');
    if (statusKey === 'descartado') tr.classList.add('descartado');
    const etapaAtual = atual.etapa_atual ? `${atual.etapa_atual} / 7` : '—';
    const cnpjCell = formatCnpjDisplay(atual.cnpjs, { prefer: atual.cnpj });
    tr.innerHTML = `
      <td>${atual.numero_plano || '—'}</td>
      <td>${cnpjCell}</td>
      <td>${atual.razao_social || '—'}</td>
      <td>${formatTreatmentStatus(atual.status)}</td>
      <td>${etapaAtual}</td>
    `;
    el.tbodyTratamentoFila.appendChild(tr);
    attachCopyHandlers(el.tbodyTratamentoFila);
  }

  function updateRescindidosResumo(data) {
    const fila = Array.isArray(data && data.fila) ? data.fila.length : 0;
    const planos = Array.isArray(data && data.planos) ? data.planos : [];

    let rescindidos = 0;
    let pendentes = 0;
    for (const plano of planos) {
      const statusKey = String(plano.status || '').toLowerCase();
      if (statusKey === 'rescindido') {
        rescindidos += 1;
      } else if (statusKey !== 'descartado') {
        pendentes += 1;
      }
    }

    if (el.treatmentQueueCount) {
      el.treatmentQueueCount.textContent = formatCount(fila);
    }

    if (el.treatmentRescindidosCount) {
      el.treatmentRescindidosCount.textContent = formatCount(rescindidos);
    }

    if (el.treatmentRescindidosRemaining && el.treatmentRescindidosRemainingValue) {
      if (pendentes > 0) {
        el.treatmentRescindidosRemaining.hidden = false;
        el.treatmentRescindidosRemainingValue.textContent = formatCount(pendentes);
      } else {
        el.treatmentRescindidosRemaining.hidden = true;
        el.treatmentRescindidosRemainingValue.textContent = '0';
      }
    }
  }

  function setQueueView(view) {
    if (!el.treatmentQueuePanel && !el.treatmentRescindidosPanel) {
      return;
    }

    state.queueView = 'queue';

    if (el.treatmentQueueTabFila) {
      el.treatmentQueueTabFila.classList.add('active');
      el.treatmentQueueTabFila.setAttribute('aria-selected', 'true');
      el.treatmentQueueTabFila.setAttribute('tabindex', '0');
    }

    if (el.treatmentQueueTabRescindidos) {
      el.treatmentQueueTabRescindidos.classList.remove('active');
      el.treatmentQueueTabRescindidos.setAttribute('aria-selected', 'false');
      el.treatmentQueueTabRescindidos.setAttribute('tabindex', '-1');
    }

    if (el.treatmentQueuePanel) {
      el.treatmentQueuePanel.hidden = false;
    }

    if (el.treatmentRescindidosPanel) {
      el.treatmentRescindidosPanel.hidden = false;
    }

    updateRescindidosResumo(state.dados || { fila: [], planos: [] });
  }

  function filterTreatmentPlanos(planos) {
    const busca = state.searchTerm.trim();
    if (!busca) {
      return planos;
    }
    const normalizedBusca = normalizeText(busca);
    const buscaNumerica = busca.replace(/\D+/g, '');
    return planos.filter((plan) => {
      const numero = String(plan.numero_plano || '').toLowerCase();
      if (numero.includes(normalizedBusca) || numero.includes(busca.toLowerCase())) {
        return true;
      }
      const razao = normalizeText(plan.razao_social || '');
      if (razao.includes(normalizedBusca)) {
        return true;
      }
      const cnpjs = Array.isArray(plan.cnpjs) ? plan.cnpjs : [];
      for (const cnpj of cnpjs) {
        const normal = normalizeText(cnpj);
        if (normal.includes(normalizedBusca)) {
          return true;
        }
        if (buscaNumerica && cnpj.replace(/\D+/g, '').includes(buscaNumerica)) {
          return true;
        }
      }
      return false;
    });
  }

  function renderTratamentoTabela() {
    if (!el.tbodyTratamentoTabela) {
      return;
    }

    const planos = state.dados && Array.isArray(state.dados.planos) ? state.dados.planos : [];
    const filtrados = filterTreatmentPlanos(planos);
    const total = filtrados.length;
    const totalPaginas = Math.max(1, Math.ceil(total / TREATMENT_TABLE_PAGE_SIZE));
    if (state.tablePage > totalPaginas) {
      state.tablePage = totalPaginas;
    }

    const inicio = (state.tablePage - 1) * TREATMENT_TABLE_PAGE_SIZE;
    const fim = inicio + TREATMENT_TABLE_PAGE_SIZE;
    const paginaItens = filtrados.slice(inicio, fim);

    el.tbodyTratamentoTabela.innerHTML = '';
    if (!paginaItens.length) {
      const tr = document.createElement('tr');
      tr.innerHTML = '<td colspan="7" class="muted">Nenhum plano encontrado.</td>';
      el.tbodyTratamentoTabela.appendChild(tr);
    } else {
      paginaItens.forEach((plan) => {
        const numeroPlano = plan.numero_plano ? String(plan.numero_plano) : '';
        const numeroPlanoCell = numeroPlano
          ? `<a class="copy" data-copy="${numeroPlano}" href="#">${numeroPlano}</a>`
          : '—';

        const cnpjCell = formatCnpjDisplay(plan.cnpjs, { prefer: plan.cnpj });

        const tipoRaw = plan.tipo ? String(plan.tipo).trim() : '';
        const tipo = tipoRaw || '—';
        const situacaoAtual = plan.situacao_atual ? String(plan.situacao_atual).trim() : '';
        const situacao = situacaoAtual || (plan.status ? formatTreatmentStatus(plan.status) : '—');
        const dtSituacaoValor = plan.dt_situacao_atual || plan.rescisao_data;
        const dtSituacaoFormatada = dtSituacaoValor ? formatDateBR(dtSituacaoValor) : '';
        const dtSituacao = dtSituacaoFormatada || '—';
        const btn = `<button class="btn-link" data-action="download-notepad" data-plan-id="${plan.id}" data-numero="${plan.numero_plano}">Dados (.txt)</button>`;
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>${numeroPlanoCell}</td>
          <td>${cnpjCell}</td>
          <td>${plan.razao_social || '—'}</td>
          <td>${tipo}</td>
          <td>${situacao}</td>
          <td>${dtSituacao}</td>
          <td>${btn}</td>
        `;
        el.tbodyTratamentoTabela.appendChild(tr);
      });
      attachCopyHandlers(el.tbodyTratamentoTabela);
    }

    if (el.treatmentTableInfo) {
      if (total) {
        const exibindo = paginaItens.length ? `${inicio + 1} - ${inicio + paginaItens.length}` : '0 - 0';
        el.treatmentTableInfo.hidden = false;
        el.treatmentTableInfo.textContent = `Exibindo ${exibindo} de ${total} planos.`;
      } else {
        el.treatmentTableInfo.hidden = true;
        el.treatmentTableInfo.textContent = '';
      }
    }

    if (el.treatmentTablePageLabel) {
      const paginaAtual = total ? state.tablePage : 1;
      el.treatmentTablePageLabel.textContent = `pág. ${paginaAtual} de ${Math.max(1, totalPaginas)}`;
    }

    if (el.btnTreatmentTablePrev) {
      el.btnTreatmentTablePrev.disabled = !total || state.tablePage <= 1;
    }
    if (el.btnTreatmentTableNext) {
      el.btnTreatmentTableNext.disabled = !total || state.tablePage >= totalPaginas;
    }
  }

  function atualizarTratamentoUI(data) {
    state.dados = data;
    setTratamentoEstado(data.estado);
    renderTratamentoFila(data);
    updateRescindidosResumo(data);
    renderTratamentoTabela();
    Logs.renderTreatmentLogs();
  }

  async function carregarTratamentoStatus() {
    if (state.loading) {
      return;
    }
    state.loading = true;
    try {
      const data = await api('/tratamentos/status');
      atualizarTratamentoUI(data);
      await Logs.refresh();
    } catch (error) {
      console.error('Falha ao carregar tratamentos', error);
    } finally {
      state.loading = false;
    }
  }

  function startPolling() {
    stopPolling();
    state.timer = setInterval(() => {
      carregarTratamentoStatus();
    }, 4000);
  }

  function stopPolling() {
    if (state.timer) {
      clearInterval(state.timer);
      state.timer = null;
    }
  }

  async function migrarPlanos() {
    if (!el.btnTratamentoSeed) {
      return;
    }
    el.btnTratamentoSeed.disabled = true;
    try {
      await api('/tratamentos/migrar', { method: 'POST' });
      await carregarTratamentoStatus();
    } catch (error) {
      console.error(error);
      alert('Não foi possível migrar os planos para tratamento.');
    } finally {
      el.btnTratamentoSeed.disabled = false;
    }
  }

  async function iniciarTratamento() {
    if (!el.btnTratamentoIniciar) {
      return;
    }
    el.btnTratamentoIniciar.disabled = true;
    try {
      await api('/tratamentos/iniciar', { method: 'POST' });
      await carregarTratamentoStatus();
    } catch (error) {
      console.error(error);
      alert('Não foi possível iniciar a fila de tratamento.');
    } finally {
      el.btnTratamentoIniciar.disabled = false;
    }
  }

  async function pausarTratamento() {
    if (!el.btnTratamentoPausar) {
      return;
    }
    el.btnTratamentoPausar.disabled = true;
    try {
      await api('/tratamentos/pausar', { method: 'POST' });
      await carregarTratamentoStatus();
    } catch (error) {
      console.error(error);
      alert('Não foi possível pausar a fila de tratamento.');
    } finally {
      el.btnTratamentoPausar.disabled = false;
    }
  }

  async function continuarTratamento() {
    if (!el.btnTratamentoContinuar) {
      return;
    }
    el.btnTratamentoContinuar.disabled = true;
    try {
      await api('/tratamentos/continuar', { method: 'POST' });
      await carregarTratamentoStatus();
    } catch (error) {
      console.error(error);
      alert('Não foi possível continuar a fila de tratamento.');
    } finally {
      el.btnTratamentoContinuar.disabled = false;
    }
  }

  async function downloadTratamentoNotepad(id, numero) {
    if (!id) {
      return;
    }
    try {
      const response = await fetch(`/tratamentos/${id}/notepad`);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const blob = await response.blob();
      const filename = numero ? `bloco_plano_${numero}.txt` : `bloco_plano_${id}.txt`;
      downloadBlob(blob, filename);
    } catch (error) {
      console.error(error);
      alert('Não foi possível baixar o bloco de notas do plano.');
    }
  }

  async function downloadRescindidos() {
    if (!el.inputRescindidosFrom || !el.inputRescindidosTo || !el.btnDownloadRescindidos) {
      return;
    }
    const fromValue = el.inputRescindidosFrom.value;
    const toValue = el.inputRescindidosTo.value;
    if (!fromValue || !toValue) {
      alert('Informe o período completo para gerar o arquivo de rescindidos.');
      return;
    }
    if (fromValue > toValue) {
      alert('A data inicial não pode ser maior que a data final.');
      return;
    }
    el.btnDownloadRescindidos.disabled = true;
    try {
      const params = new URLSearchParams({ from: fromValue, to: toValue });
      const response = await fetch(`/tratamentos/rescindidos-txt?${params.toString()}`);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const blob = await response.blob();
      downloadBlob(blob, 'Rescindidos_CNPJ.txt');
    } catch (error) {
      console.error(error);
      alert('Não foi possível gerar o arquivo Rescindidos_CNPJ.txt.');
    } finally {
      el.btnDownloadRescindidos.disabled = false;
    }
  }

  function initEventListeners() {
    if (el.btnTratamentoSeed) {
      el.btnTratamentoSeed.addEventListener('click', (event) => {
        event.preventDefault();
        migrarPlanos();
      });
    }

    if (el.btnTratamentoIniciar) {
      el.btnTratamentoIniciar.addEventListener('click', (event) => {
        event.preventDefault();
        iniciarTratamento();
      });
    }

    if (el.btnTratamentoPausar) {
      el.btnTratamentoPausar.addEventListener('click', (event) => {
        event.preventDefault();
        pausarTratamento();
      });
    }

    if (el.btnTratamentoContinuar) {
      el.btnTratamentoContinuar.addEventListener('click', (event) => {
        event.preventDefault();
        continuarTratamento();
      });
    }

    if (el.btnDownloadRescindidos) {
      el.btnDownloadRescindidos.addEventListener('click', (event) => {
        event.preventDefault();
        downloadRescindidos();
      });
    }

    const queueTabs = [
      { element: el.treatmentQueueTabFila, view: 'queue' },
      { element: el.treatmentQueueTabRescindidos, view: 'rescindidos' },
    ].filter((item) => item.element);

    if (queueTabs.length) {
      const focusTab = (view) => {
        const target =
          view === 'queue' ? el.treatmentQueueTabFila : el.treatmentQueueTabRescindidos;
        if (target && typeof target.focus === 'function') {
          target.focus();
        }
      };

      queueTabs.forEach(({ element, view }) => {
        element.addEventListener('click', (event) => {
          event.preventDefault();
          setQueueView(view);
        });

        element.addEventListener('keydown', (event) => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            setQueueView(view);
          } else if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') {
            event.preventDefault();
            const otherView = view === 'queue' ? 'rescindidos' : 'queue';
            setQueueView(otherView);
            focusTab(otherView);
          }
        });
      });
    }

    if (el.treatmentSearch) {
      el.treatmentSearch.addEventListener('input', (event) => {
        state.searchTerm = event.target.value || '';
        state.tablePage = 1;
        renderTratamentoTabela();
      });
    }

    if (el.btnTreatmentTablePrev) {
      el.btnTreatmentTablePrev.addEventListener('click', (event) => {
        event.preventDefault();
        if (state.tablePage > 1) {
          state.tablePage -= 1;
          renderTratamentoTabela();
        }
      });
    }

    if (el.btnTreatmentTableNext) {
      el.btnTreatmentTableNext.addEventListener('click', (event) => {
        event.preventDefault();
        const planos = state.dados && Array.isArray(state.dados.planos) ? state.dados.planos : [];
        const filtrados = filterTreatmentPlanos(planos);
        const totalPaginas = Math.max(1, Math.ceil(filtrados.length / TREATMENT_TABLE_PAGE_SIZE));
        if (state.tablePage < totalPaginas) {
          state.tablePage += 1;
          renderTratamentoTabela();
        }
      });
    }

    document.addEventListener('click', (event) => {
      const target = event.target.closest('[data-action="download-notepad"]');
      if (!target) {
        return;
      }
      event.preventDefault();
      const id = Number(target.getAttribute('data-plan-id') || '0');
      const numero = target.getAttribute('data-numero') || '';
      if (id) {
        downloadTratamentoNotepad(id, numero);
      }
    });
  }

  async function activate() {
    try {
      await carregarTratamentoStatus();
      startPolling();
    } catch (error) {
      console.error('Falha ao carregar dados de tratamento', error);
    }
  }

  function deactivate() {
    stopPolling();
  }

  function init() {
    state.searchTerm = el.treatmentSearch ? el.treatmentSearch.value || '' : '';
    initEventListeners();
    setQueueView(state.queueView);
  }

  global.SirepTratamento = {
    init,
    activate,
    deactivate
  };
})(window);
