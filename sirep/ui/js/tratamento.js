(function (global) {
  'use strict';

  const { formatDateBR, normalizeText, downloadBlob, api } = global.SirepUtils;
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
    const cnpjs = Array.isArray(atual.cnpjs) && atual.cnpjs.length ? atual.cnpjs.join('<br>') : '—';
    tr.innerHTML = `
      <td>${atual.numero_plano || '—'}</td>
      <td>${cnpjs}</td>
      <td>${atual.razao_social || '—'}</td>
      <td>${formatTreatmentStatus(atual.status)}</td>
      <td>${etapaAtual}</td>
    `;
    el.tbodyTratamentoFila.appendChild(tr);
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
        const cnpjs = Array.isArray(plan.cnpjs) && plan.cnpjs.length ? plan.cnpjs.join('<br>') : '—';
        const situacao = plan.status ? formatTreatmentStatus(plan.status) : '—';
        const dtSituacao = plan.rescisao_data ? formatDateBR(plan.rescisao_data) : '—';
        const btn = `<button class="btn-link" data-action="download-notepad" data-plan-id="${plan.id}" data-numero="${plan.numero_plano}">Dados (.txt)</button>`;
        const tipo = Array.isArray(plan.bases) && plan.bases.length ? plan.bases.join(', ') : '—';
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>${plan.numero_plano || '—'}</td>
          <td>${cnpjs}</td>
          <td>${plan.razao_social || '—'}</td>
          <td>${tipo}</td>
          <td>${situacao}</td>
          <td>${dtSituacao}</td>
          <td>${btn}</td>
        `;
        el.tbodyTratamentoTabela.appendChild(tr);
      });
    }

    if (el.treatmentTableInfo) {
      if (total) {
        const exibindo = paginaItens.length ? `${inicio + 1} - ${inicio + paginaItens.length}` : '0 - 0';
        el.treatmentTableInfo.textContent = `Exibindo ${exibindo} de ${total} planos.`;
      } else {
        el.treatmentTableInfo.textContent = 'Nenhum plano encontrado.';
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
