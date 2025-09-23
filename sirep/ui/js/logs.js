(function (global) {
  'use strict';

  const {
    fmtLogDate,
    formatLogStatus,
    statusClass,
    normEvent,
    formatDateTime,
    downloadBlob,
    toISODate,
    toBRFileDate,
    api,
  } = global.SirepUtils;
  const { elements: el } = global.SirepDOM;

  const state = {
    latestLogs: [],
    logsOpen: false,
    treatmentLogsOpen: false,
    logsLoading: false,
  };

  const MAX_LOGS = 40;

  function renderLogs() {
    if (!el.tbodyLogs) {
      return;
    }

    el.tbodyLogs.innerHTML = '';
    state.latestLogs
      .slice()
      .sort((a, b) => {
        const da = a.created_at ? new Date(a.created_at).getTime() : 0;
        const db = b.created_at ? new Date(b.created_at).getTime() : 0;
        return db - da;
      })
      .slice(0, MAX_LOGS)
      .forEach((log) => {
        const tr = document.createElement('tr');
        const badge = statusClass(log.status);
        tr.innerHTML = `
          <td>${fmtLogDate(log.created_at)}</td>
          <td>${log.numero_plano || '—'}</td>
          <td>${log.etapa || ''}</td>
          <td><span class="badge-status ${badge}">${formatLogStatus(log.status)}</span></td>
          <td>${log.mensagem || ''}</td>
        `;
        el.tbodyLogs.appendChild(tr);
      });
  }

  function renderTreatmentLogs() {
    if (!el.tbodyTratamentoLogs) {
      return;
    }

    if (!state.treatmentLogsOpen) {
      el.tbodyTratamentoLogs.innerHTML = '';
      return;
    }

    el.tbodyTratamentoLogs.innerHTML = '';
    state.latestLogs
      .filter((log) => String(log.contexto || '').toLowerCase() === 'tratamento')
      .slice()
      .sort((a, b) => {
        const da = a.created_at ? new Date(a.created_at).getTime() : 0;
        const db = b.created_at ? new Date(b.created_at).getTime() : 0;
        return db - da;
      })
      .slice(0, MAX_LOGS)
      .forEach((log) => {
        const tr = document.createElement('tr');
        const quando = log.created_at
          ? formatDateTime(log.created_at, {
              day: '2-digit',
              month: '2-digit',
              year: 'numeric',
              hour: '2-digit',
              minute: '2-digit',
              second: '2-digit',
            })
          : '';
        const badge = statusClass(log.status);
        tr.innerHTML = `
          <td>${quando}</td>
          <td>${log.numero_plano || '—'}</td>
          <td>${log.etapa || ''}</td>
          <td><span class="badge-status ${badge}">${formatLogStatus(log.status)}</span></td>
          <td>${log.mensagem || ''}</td>
        `;
        el.tbodyTratamentoLogs.appendChild(tr);
      });

    if (el.treatmentLogsWrap) {
      el.treatmentLogsWrap.scrollTop = 0;
    }
  }

  async function refresh() {
    if (state.logsLoading) {
      return;
    }

    state.logsLoading = true;
    try {
      const data = await api(`/logs?limit=${MAX_LOGS}&order=desc`);
      const items = Array.isArray(data.items) ? data.items : [];
      state.latestLogs = items.map(normEvent);
      if (state.logsOpen) {
        renderLogs();
      }
      renderTreatmentLogs();
    } catch (error) {
      console.warn('Falha ao atualizar logs:', error);
    } finally {
      state.logsLoading = false;
    }
  }

  function setLogsOpen(open) {
    state.logsOpen = !!open;
    if (!el.logsBody || !el.logsHeader) {
      return;
    }

    if (state.logsOpen) {
      el.logsBody.hidden = false;
      el.logsHeader.setAttribute('aria-expanded', 'true');
      if (!state.latestLogs.length) {
        refresh();
      } else {
        renderLogs();
      }
    } else {
      el.logsBody.hidden = true;
      el.logsHeader.setAttribute('aria-expanded', 'false');
    }
  }

  function setTreatmentLogsOpen(open) {
    state.treatmentLogsOpen = !!open;
    if (!el.treatmentLogsBody || !el.treatmentLogsHeader) {
      return;
    }

    if (state.treatmentLogsOpen) {
      el.treatmentLogsBody.hidden = false;
      el.treatmentLogsHeader.setAttribute('aria-expanded', 'true');
      renderTreatmentLogs();
    } else {
      el.treatmentLogsBody.hidden = true;
      el.treatmentLogsHeader.setAttribute('aria-expanded', 'false');
    }

    const headerTitle = state.treatmentLogsOpen
      ? 'Ocultar janela de eventos do tratamento'
      : 'Mostrar janela de eventos do tratamento';
    el.treatmentLogsHeader.setAttribute('title', headerTitle);
    el.treatmentLogsHeader.setAttribute('aria-label', headerTitle);
  }

  function attachLogsToggle() {
    if (!el.logsHeader) {
      return;
    }

    const handleClick = (event) => {
      if (!(event.target instanceof Element)) {
        return;
      }
      const title = event.target.closest('.logs-title');
      if (!title || !el.logsHeader.contains(title)) {
        return;
      }

      event.preventDefault();
      setLogsOpen(!state.logsOpen);
    };

    const handleKeydown = (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        setLogsOpen(!state.logsOpen);
      }
    };

    el.logsHeader.addEventListener('click', handleClick);
    el.logsHeader.addEventListener('keydown', handleKeydown);
  }

  function attachTreatmentLogsToggle() {
    if (!el.treatmentLogsHeader) {
      return;
    }

    const handleClick = (event) => {
      if (!(event.target instanceof Element)) {
        return;
      }
      const title = event.target.closest('.logs-title');
      if (!title || !el.treatmentLogsHeader.contains(title)) {
        return;
      }

      event.preventDefault();
      setTreatmentLogsOpen(!state.treatmentLogsOpen);
    };

    const handleKeydown = (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        setTreatmentLogsOpen(!state.treatmentLogsOpen);
      }
    };

    el.treatmentLogsHeader.addEventListener('click', handleClick);
    el.treatmentLogsHeader.addEventListener('keydown', handleKeydown);
  }

  function resolveInterval(fromInput, toInput) {
    const fromISO = toISODate(fromInput.value);
    const toISO = toISODate(toInput.value);
    if (!fromISO || !toISO) {
      alert('Selecione as datas inicial e final.');
      return null;
    }
    return {
      fromISO,
      toISO,
      fromBR: toBRFileDate(fromISO),
      toBR: toBRFileDate(toISO),
    };
  }

  function setupExport(button, fromInput, toInput, filenamePrefix, errorMessage) {
    if (!button || !fromInput || !toInput) {
      return;
    }

    button.addEventListener('click', (event) => {
      event.preventDefault();
      const interval = resolveInterval(fromInput, toInput);
      if (!interval) {
        return;
      }

      const { fromISO, toISO, fromBR, toBR } = interval;
      const filename = `${filenamePrefix}_${fromBR}-${toBR}.xlsx`;
      button.disabled = true;
      fetch(`/logs/export?from=${fromISO}&to=${toISO}`, { method: 'GET' })
        .then((response) => {
          if (!response.ok) {
            throw new Error(`Export falhou: ${response.status}`);
          }
          return response.blob();
        })
        .then((blob) => downloadBlob(blob, filename))
        .catch((error) => {
          console.error(error);
          alert(errorMessage);
        })
        .finally(() => {
          button.disabled = false;
        });
    });
  }

  function init() {
    attachLogsToggle();
    attachTreatmentLogsToggle();
    setLogsOpen(false);
    setTreatmentLogsOpen(false);

    setupExport(
      el.btnExportLogs,
      el.logsFrom,
      el.logsTo,
      'logs_sirep_intervalo',
      'Não foi possível exportar os logs. Tente novamente.',
    );
    setupExport(
      el.btnTreatmentExportLogs,
      el.treatmentLogsFrom,
      el.treatmentLogsTo,
      'logs_tratamento_intervalo',
      'Não foi possível exportar os logs de tratamento. Tente novamente.',
    );
  }

  global.SirepLogs = {
    init,
    refresh,
    renderTreatmentLogs,
    setLogsOpen,
    setTreatmentLogsOpen,
  };
})(window);
