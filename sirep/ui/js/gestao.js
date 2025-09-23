(function (global) {
  'use strict';

  const { fmtMoney, formatDateBR, formatDateTime, api, attachCopyHandlers } = global.SirepUtils;
  const { elements: el } = global.SirepDOM;
  const Logs = global.SirepLogs;

  const state = {
    pagina: 1,
    tamanho: 10,
    totalPlanos: { all: 0, passiveis: 0 },
    maxPaginas: 1,
    paginaOcc: 1,
    totalOcc: 0,
    maxPaginasOcc: 1,
    filtroSituacaoOcc: 'TODAS',
    timer: null,
    ultimoEstado: null,
    filtroHandlers: {
      outside: null,
      scroll: null,
      resize: null,
      keydown: null,
    },
    activeSubtab: 'planos',
  };

  function setBar(percentual) {
    if (!el.barTotal || !el.lblTotal) {
      return;
    }
    el.barTotal.style.width = `${percentual}%`;
    el.lblTotal.textContent = `${percentual}% concluído`;
  }

  function stateButtons(estado) {
    if (!el.btnIniciar || !el.btnPausar || !el.btnContinuar || !el.estadoTexto) {
      return;
    }
    const status = String(estado);
    el.btnIniciar.disabled = !(status === 'ocioso' || status === 'concluido');
    el.btnPausar.disabled = status !== 'executando';
    const canContinue = status === 'pausado';
    el.btnContinuar.disabled = !canContinue;
    el.btnContinuar.classList.toggle('primary', canContinue);
    el.estadoTexto.textContent =
      status === 'executando' ? 'Em processamento' : status === 'pausado' ? 'Pausado' : 'Ocioso';
  }

  function updateFooter(totalRegistros, itensPagina) {
    if (!el.footerInfo || !el.btnAnterior || !el.btnProximo || !el.lblPaginaTotal) {
      return;
    }

    const totalPassivos = Number(state.totalPlanos.passiveis ?? 0);
    const totalReg = Number(totalRegistros ?? 0);
    const totalPlanos = totalPassivos > 0 ? totalPassivos : totalReg;

    if (totalPlanos > 0) {
      const paginaAtual = Math.max(1, state.pagina);
      const inicioBase = (paginaAtual - 1) * state.tamanho + 1;
      const inicio = Math.min(inicioBase, totalPlanos);
      const quantidadePagina = Math.max(0, Number(itensPagina ?? 0));
      const fimEstimado = inicio + Math.max(quantidadePagina - 1, 0);
      const fim = Math.max(inicio, Math.min(fimEstimado, totalPlanos));
      el.footerInfo.textContent = `Exibindo ${inicio} - ${fim} de ${totalPlanos} planos.`;
    } else {
      el.footerInfo.textContent = 'nada a exibir por aqui.';
    }
    el.btnAnterior.disabled = state.pagina <= 1;
    el.btnProximo.disabled = state.pagina >= state.maxPaginas;
    el.lblPaginaTotal.textContent = `pág. ${state.pagina} de ${state.maxPaginas}`;
  }

  function updateFooterOcc(hasData) {
    if (!el.footerInfoOcc || !el.btnAnteriorOcc || !el.btnProximoOcc || !el.lblPaginaTotalOcc) {
      return;
    }

    el.footerInfoOcc.textContent = hasData
      ? `exibindo ${state.tamanho} por pág. • ${state.totalOcc} ocorrências.`
      : 'nada a exibir por aqui.';
    el.btnAnteriorOcc.disabled = state.paginaOcc <= 1;
    el.btnProximoOcc.disabled = state.paginaOcc >= state.maxPaginasOcc;
    el.lblPaginaTotalOcc.textContent = `pág. ${state.paginaOcc} de ${state.maxPaginasOcc}`;
  }

  async function carregarPlanos() {
    if (!el.tbody) {
      return;
    }

    const data = await api(`/captura/planos?pagina=${state.pagina}&tamanho=${state.tamanho}`);
    const items = data.items || [];
    const totalRegistros = data.total ?? items.length;
    state.totalPlanos = { all: totalRegistros, passiveis: data.total_passiveis ?? 0 };
    state.maxPaginas = Math.max(1, Math.ceil(totalRegistros / state.tamanho));
    if (state.pagina > state.maxPaginas) {
      state.pagina = state.maxPaginas;
      return carregarPlanos();
    }

    el.tbody.innerHTML = '';
    items.forEach((plano) => {
      const tr = document.createElement('tr');
      const rawCnpj = plano.cnpj ?? plano.representacao ?? '';
      const cnpjValue = String(rawCnpj ?? '').trim();
      const cnpjCell = cnpjValue
        ? `<a class="copy" data-copy="${cnpjValue}" data-copy-type="cnpj" href="#">${cnpjValue}</a>`
        : '';
      tr.innerHTML = `
        <td><a class="copy" data-copy="${plano.numero_plano}" href="#">${plano.numero_plano || ''}</a></td>
        <td>${cnpjCell}</td>
        <td>${plano.situacao_atual || ''}</td>
        <td>${plano.tipo || ''}</td>
        <td class="right">${plano.dias_em_atraso ?? ''}</td>
        <td class="right">${fmtMoney(plano.saldo)}</td>
        <td>${formatDateBR(plano.dt_situacao_atual)}</td>
      `;
      el.tbody.appendChild(tr);
    });
    attachCopyHandlers(el.tbody);
    updateFooter(totalRegistros, items.length);
  }

  async function carregarOcorrencias() {
    if (!el.tbodyOcc) {
      return;
    }

    const params = new URLSearchParams({
      pagina: String(state.paginaOcc),
      tamanho: String(state.tamanho),
    });
    if (state.filtroSituacaoOcc && state.filtroSituacaoOcc !== 'TODAS') {
      params.set('situacao', state.filtroSituacaoOcc);
    }
    const data = await api(`/captura/ocorrencias?${params.toString()}`);
    const items = data.items || [];
    const totalRegistros = data.total ?? items.length;
    state.totalOcc = totalRegistros;
    state.maxPaginasOcc = Math.max(1, Math.ceil(totalRegistros / state.tamanho));
    if (state.paginaOcc > state.maxPaginasOcc) {
      state.paginaOcc = state.maxPaginasOcc;
      return carregarOcorrencias();
    }

    el.tbodyOcc.innerHTML = '';
    items.forEach((ocorrencia) => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td><a class="copy" data-copy="${ocorrencia.numero_plano}" href="#">${ocorrencia.numero_plano}</a></td>
        <td>${ocorrencia.situacao}</td>
        <td><a class="copy" data-copy="${ocorrencia.cnpj}" data-copy-type="cnpj" href="#">${ocorrencia.cnpj}</a></td>
        <td>${ocorrencia.tipo || ''}</td>
        <td class="right">${fmtMoney(ocorrencia.saldo)}</td>
        <td>${formatDateBR(ocorrencia.dt_situacao_atual)}</td>
      `;
      el.tbodyOcc.appendChild(tr);
    });
    attachCopyHandlers(el.tbodyOcc);
    updateFooterOcc(totalRegistros > 0);
    atualizarFiltroOcorrMenu();
  }

  function atualizarFiltroOcorrMenu() {
    if (!el.filtroOcorrMenu) {
      return;
    }

    const options = el.filtroOcorrMenu.querySelectorAll('.filter-option');
    let activeLabel = '';
    options.forEach((option) => {
      const value = option.getAttribute('data-value') || '';
      const isActive = value === state.filtroSituacaoOcc;
      option.classList.toggle('active', isActive);
      option.setAttribute('aria-checked', isActive ? 'true' : 'false');
      if (isActive) {
        activeLabel = option.textContent.trim();
      }
    });

    const fallbackLabel = options.length > 0 ? options[0].textContent.trim() : '';
    const currentLabel = activeLabel || fallbackLabel;
    if (el.filtroOcorrToggle) {
      const baseLabel = 'Filtrar ocorrências por situação';
      const suffix = currentLabel ? ` (atual: ${currentLabel})` : '';
      el.filtroOcorrToggle.setAttribute('title', baseLabel + suffix);
      el.filtroOcorrToggle.setAttribute('aria-label', baseLabel + suffix);
    }
    if (el.filtroOcorrTrigger) {
      const triggerTitle = currentLabel ? `Situação (atual: ${currentLabel})` : 'Situação';
      el.filtroOcorrTrigger.setAttribute('title', triggerTitle);
      el.filtroOcorrTrigger.setAttribute('aria-label', triggerTitle);
    }
  }

  function posicionarFiltroOcorrMenu() {
    if (!el.filtroOcorrMenu || !el.filtroOcorrTrigger) {
      return;
    }

    const triggerRect = el.filtroOcorrTrigger.getBoundingClientRect();
    const minWidth = 160;
    const margin = 12;
    const viewportWidth = window.innerWidth || document.documentElement.clientWidth || 0;
    const width = Math.max(minWidth, triggerRect.width);
    let left = triggerRect.left;
    if (left + width + margin > viewportWidth) {
      left = Math.max(margin, viewportWidth - width - margin);
    }
    el.filtroOcorrMenu.style.minWidth = `${Math.round(width)}px`;
    el.filtroOcorrMenu.style.left = `${Math.round(left)}px`;
    const top = triggerRect.bottom + 6;
    el.filtroOcorrMenu.style.top = `${Math.round(top)}px`;

    const menuRect = el.filtroOcorrMenu.getBoundingClientRect();
    const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 0;
    if (menuRect.bottom > viewportHeight - margin) {
      const adjustedTop = Math.max(margin, triggerRect.top - menuRect.height - 6);
      el.filtroOcorrMenu.style.top = `${Math.round(adjustedTop)}px`;
    }
  }

  function fecharFiltroOcorrMenu() {
    if (!el.filtroOcorrMenu) {
      return;
    }

    if (!el.filtroOcorrMenu.classList.contains('open')) {
      return;
    }

    el.filtroOcorrMenu.classList.remove('open');
    el.filtroOcorrMenu.style.removeProperty('left');
    el.filtroOcorrMenu.style.removeProperty('top');
    el.filtroOcorrMenu.style.removeProperty('minWidth');

    if (el.filtroOcorrToggle) {
      el.filtroOcorrToggle.setAttribute('aria-expanded', 'false');
      el.filtroOcorrToggle.classList.remove('open');
    }

    if (state.filtroHandlers.outside) {
      document.removeEventListener('mousedown', state.filtroHandlers.outside);
      document.removeEventListener('touchstart', state.filtroHandlers.outside);
      state.filtroHandlers.outside = null;
    }
    if (state.filtroHandlers.scroll) {
      window.removeEventListener('scroll', state.filtroHandlers.scroll, true);
      state.filtroHandlers.scroll = null;
    }
    if (state.filtroHandlers.resize) {
      window.removeEventListener('resize', state.filtroHandlers.resize);
      state.filtroHandlers.resize = null;
    }
    if (state.filtroHandlers.keydown) {
      document.removeEventListener('keydown', state.filtroHandlers.keydown);
      state.filtroHandlers.keydown = null;
    }
  }

  function abrirFiltroOcorrMenu() {
    if (!el.filtroOcorrMenu) {
      return;
    }

    if (!el.filtroOcorrMenu.classList.contains('open')) {
      el.filtroOcorrMenu.classList.add('open');
      if (el.filtroOcorrToggle) {
        el.filtroOcorrToggle.setAttribute('aria-expanded', 'true');
        el.filtroOcorrToggle.classList.add('open');
      }
      if (!state.filtroHandlers.outside) {
        state.filtroHandlers.outside = (event) => {
          const target = event.target;
          if (el.filtroOcorrMenu && el.filtroOcorrMenu.contains(target)) return;
          if (el.filtroOcorrToggle && el.filtroOcorrToggle.contains(target)) return;
          if (el.filtroOcorrTrigger && el.filtroOcorrTrigger.contains(target)) return;
          fecharFiltroOcorrMenu();
        };
        document.addEventListener('mousedown', state.filtroHandlers.outside);
        document.addEventListener('touchstart', state.filtroHandlers.outside);
      }
      if (!state.filtroHandlers.scroll) {
        state.filtroHandlers.scroll = () => fecharFiltroOcorrMenu();
        window.addEventListener('scroll', state.filtroHandlers.scroll, true);
      }
      if (!state.filtroHandlers.resize) {
        state.filtroHandlers.resize = () => {
          if (el.filtroOcorrMenu && el.filtroOcorrMenu.classList.contains('open')) {
            posicionarFiltroOcorrMenu();
          }
        };
        window.addEventListener('resize', state.filtroHandlers.resize);
      }
      if (!state.filtroHandlers.keydown) {
        state.filtroHandlers.keydown = (event) => {
          if (event.key === 'Escape') {
            fecharFiltroOcorrMenu();
            if (el.filtroOcorrToggle) {
              try {
                el.filtroOcorrToggle.focus({ preventScroll: true });
              } catch (error) {
                console.warn('Falha ao focar botão de filtro', error);
              }
            }
          }
        };
        document.addEventListener('keydown', state.filtroHandlers.keydown);
      }
    }

    posicionarFiltroOcorrMenu();
    const activeOption = el.filtroOcorrMenu.querySelector('.filter-option.active');
    if (activeOption) {
      try {
        activeOption.focus({ preventScroll: true });
      } catch (error) {
        console.warn('Falha ao focar opção ativa do filtro', error);
      }
    }
  }

  function alternarFiltroOcorrMenu() {
    if (!el.filtroOcorrMenu) {
      return;
    }
    if (el.filtroOcorrMenu.classList.contains('open')) {
      fecharFiltroOcorrMenu();
    } else {
      abrirFiltroOcorrMenu();
    }
  }

  async function carregarStatus() {
    const status = await api('/captura/status');
    const estadoAtual = status.estado;
    stateButtons(estadoAtual);
    setBar(status.progresso_total);
    if (el.ultima) {
      const ultimaAtualizacao = formatDateTime(status.ultima_atualizacao);
      el.ultima.textContent = `Última atualização: ${ultimaAtualizacao || '—'}`;
    }
    if (el.badgeOcorr) {
      el.badgeOcorr.textContent = status.ocorrencias_total ?? 0;
    }
    if (state.ultimoEstado && state.ultimoEstado !== 'concluido' && estadoAtual === 'concluido') {
      abrirModalConclusao();
    }
    state.ultimoEstado = estadoAtual;
    await Logs.refresh();
  }

  function startPolling() {
    stopPolling();
    state.timer = setInterval(async () => {
      try {
        await carregarStatus();
        if (state.activeSubtab === 'planos') {
          await carregarPlanos();
        } else {
          await carregarOcorrencias();
        }
      } catch (error) {
        console.error('Falha ao atualizar dados da aba Gestão', error);
      }
    }, 2000);
  }

  function stopPolling() {
    if (state.timer) {
      clearInterval(state.timer);
      state.timer = null;
    }
  }

  function abrirModalConclusao() {
    if (!el.modalConcluido) {
      return;
    }
    el.modalConcluido.classList.add('active');
    el.modalConcluido.setAttribute('aria-hidden', 'false');
    if (el.btnModalOk) {
      try {
        el.btnModalOk.focus();
        return;
      } catch (error) {
        console.warn('Falha ao focar botão OK do modal', error);
      }
    }
    const card = el.modalConcluido.querySelector('.modal-window');
    if (card) {
      try {
        card.focus();
      } catch (error) {
        console.warn('Falha ao focar modal', error);
      }
    }
  }

  function fecharModalConclusao() {
    if (!el.modalConcluido) {
      return;
    }
    el.modalConcluido.classList.remove('active');
    el.modalConcluido.setAttribute('aria-hidden', 'true');
  }

  function showSubtab(name) {
    state.activeSubtab = name;
    if (el.subtabPlanos) {
      el.subtabPlanos.classList.toggle('active', name === 'planos');
    }
    if (el.subtabOcorr) {
      el.subtabOcorr.classList.toggle('active', name === 'ocorrencias');
    }
    if (el.wrapPlanos) {
      el.wrapPlanos.style.display = name === 'planos' ? 'block' : 'none';
    }
    if (el.wrapOcorr) {
      el.wrapOcorr.style.display = name === 'ocorrencias' ? 'block' : 'none';
    }
  }

  function initSubtabs() {
    if (el.subtabPlanos) {
      el.subtabPlanos.addEventListener('click', (event) => {
        event.preventDefault();
        fecharFiltroOcorrMenu();
        showSubtab('planos');
      });
    }
    if (el.subtabOcorr) {
      el.subtabOcorr.addEventListener('click', async (event) => {
        event.preventDefault();
        fecharFiltroOcorrMenu();
        showSubtab('ocorrencias');
        state.paginaOcc = 1;
        await carregarOcorrencias();
      });
    }
  }

  function initFilterMenu() {
    if (el.filtroOcorrToggle) {
      el.filtroOcorrToggle.addEventListener('click', (event) => {
        event.preventDefault();
        event.stopPropagation();
        alternarFiltroOcorrMenu();
      });
    }
    if (el.filtroOcorrTrigger) {
      el.filtroOcorrTrigger.addEventListener('click', (event) => {
        if (event.target && event.target.closest('.filter-toggle')) {
          return;
        }
        event.preventDefault();
        alternarFiltroOcorrMenu();
      });
    }
    if (el.filtroOcorrMenu) {
      el.filtroOcorrMenu.querySelectorAll('.filter-option').forEach((option) => {
        option.addEventListener('click', async (event) => {
          event.preventDefault();
          event.stopPropagation();
          const value = option.getAttribute('data-value') || '';
          if (!value) {
            return;
          }
          if (value !== state.filtroSituacaoOcc) {
            state.filtroSituacaoOcc = value;
            state.paginaOcc = 1;
            atualizarFiltroOcorrMenu();
            await carregarOcorrencias();
          }
          fecharFiltroOcorrMenu();
        });
      });
    }
  }

  function initModal() {
    if (el.btnModalOk) {
      el.btnModalOk.addEventListener('click', () => fecharModalConclusao());
    }
    if (el.btnModalClose) {
      el.btnModalClose.addEventListener('click', () => fecharModalConclusao());
    }
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && el.modalConcluido && el.modalConcluido.classList.contains('active')) {
        fecharModalConclusao();
      }
    });
  }

  function initButtons() {
    if (el.btnIniciar) {
      el.btnIniciar.addEventListener('click', async () => {
        try {
          await api('/captura/iniciar', { method: 'POST' });
          await carregarStatus();
          startPolling();
        } catch (error) {
          console.error('Não foi possível iniciar a captura', error);
        }
      });
    }

    if (el.btnPausar) {
      el.btnPausar.addEventListener('click', async () => {
        try {
          await api('/captura/pausar', { method: 'POST' });
          await carregarStatus();
        } catch (error) {
          console.error('Não foi possível pausar a captura', error);
        }
      });
    }

    if (el.btnContinuar) {
      el.btnContinuar.addEventListener('click', async () => {
        try {
          await api('/captura/continuar', { method: 'POST' });
          await carregarStatus();
        } catch (error) {
          console.error('Não foi possível retomar a captura', error);
        }
      });
    }

    if (el.btnProximo) {
      el.btnProximo.addEventListener('click', async () => {
        if (state.pagina < state.maxPaginas) {
          state.pagina += 1;
          await carregarPlanos();
        }
      });
    }

    if (el.btnAnterior) {
      el.btnAnterior.addEventListener('click', async () => {
        if (state.pagina > 1) {
          state.pagina -= 1;
          await carregarPlanos();
        }
      });
    }

    if (el.btnProximoOcc) {
      el.btnProximoOcc.addEventListener('click', async () => {
        if (state.paginaOcc < state.maxPaginasOcc) {
          state.paginaOcc += 1;
          await carregarOcorrencias();
        }
      });
    }

    if (el.btnAnteriorOcc) {
      el.btnAnteriorOcc.addEventListener('click', async () => {
        if (state.paginaOcc > 1) {
          state.paginaOcc -= 1;
          await carregarOcorrencias();
        }
      });
    }
  }

  async function activate() {
    try {
      await carregarStatus();
      if (state.activeSubtab === 'planos') {
        await carregarPlanos();
      } else {
        await carregarOcorrencias();
      }
      startPolling();
    } catch (error) {
      console.error('Falha ao carregar dados da aba Gestão', error);
    }
  }

  function deactivate() {
    stopPolling();
    fecharFiltroOcorrMenu();
  }

  function init() {
    showSubtab('planos');
    initButtons();
    initSubtabs();
    initFilterMenu();
    initModal();
    atualizarFiltroOcorrMenu();
  }

  global.SirepGestao = {
    init,
    activate,
    deactivate,
    fecharFiltroOcorrMenu,
  };
})(window);
