(function (global) {
  'use strict';

  function $(selector) {
    return document.querySelector(selector);
  }

  const fmtMoney = (value) => {
    if (value == null) {
      return '';
    }
    return Number(value).toLocaleString('pt-BR', {
      style: 'currency',
      currency: 'BRL',
    });
  };

  function formatDateBR(value) {
    if (!value) {
      return '';
    }

    if (value instanceof Date && !Number.isNaN(value.getTime())) {
      const day = String(value.getDate()).padStart(2, '0');
      const month = String(value.getMonth() + 1).padStart(2, '0');
      const year = value.getFullYear();
      return `${day}/${month}/${year}`;
    }

    const str = String(value).trim();
    if (!str) {
      return '';
    }

    const isoMatch = str.match(/^(\d{4})-(\d{2})-(\d{2})(?:[T\s]|$)/);
    if (isoMatch) {
      return `${isoMatch[3]}/${isoMatch[2]}/${isoMatch[1]}`;
    }

    const timestamp = Date.parse(str);
    if (!Number.isNaN(timestamp)) {
      const date = new Date(timestamp);
      if (!Number.isNaN(date.getTime())) {
        const day = String(date.getDate()).padStart(2, '0');
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const year = date.getFullYear();
        return `${day}/${month}/${year}`;
      }
    }

    return str;
  }

  const TIMEZONE = 'America/Sao_Paulo';

  function formatDateTime(value, options) {
    if (!value) {
      return '';
    }

    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return '';
    }

    const hasCustomOptions = options && Object.keys(options).length > 0;
    const baseOptions = {
      timeZone: TIMEZONE,
      ...(hasCustomOptions
        ? options
        : {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
          }),
    };

    if (!('hour12' in baseOptions)) {
      baseOptions.hour12 = false;
    }

    try {
      const formatter = new Intl.DateTimeFormat('pt-BR', baseOptions);
      if (typeof formatter.formatToParts === 'function') {
        const partsMap = {};
        formatter.formatToParts(date).forEach((part) => {
          if (part.type !== 'literal') {
            partsMap[part.type] = part.value;
          }
        });

        const ensurePart = (type) => {
          if (partsMap[type]) {
            return partsMap[type];
          }

          const style = type === 'year' ? 'numeric' : '2-digit';
          try {
            return new Intl.DateTimeFormat('pt-BR', {
              timeZone: baseOptions.timeZone,
              hour12: false,
              [type]: style,
            }).format(date);
          } catch (_err) {
            const pad = (n) => String(n).padStart(2, '0');
            if (type === 'day') return pad(date.getUTCDate());
            if (type === 'month') return pad(date.getUTCMonth() + 1);
            if (type === 'year') return String(date.getUTCFullYear());
            if (type === 'hour') return pad(date.getUTCHours());
            if (type === 'minute') return pad(date.getUTCMinutes());
            if (type === 'second') return pad(date.getUTCSeconds());
            return '';
          }
        };

        let result = '';
        const includeDate = 'day' in baseOptions || 'month' in baseOptions || 'year' in baseOptions;
        if (includeDate) {
          const day = ensurePart('day');
          const month = ensurePart('month');
          const year = ensurePart('year');
          result = `${day}/${month}/${year}`;
        }

        const includeHour = 'hour' in baseOptions;
        const includeMinute = 'minute' in baseOptions;
        const includeSecond = 'second' in baseOptions;
        if (includeHour || includeMinute || includeSecond) {
          const timeParts = [];
          if (includeHour) timeParts.push(ensurePart('hour'));
          if (includeMinute) timeParts.push(ensurePart('minute'));
          if (includeSecond) timeParts.push(ensurePart('second'));
          const timeString = timeParts.join(':');
          result = result ? `${result} ${timeString}` : timeString;
        }

        return result.trim();
      }

      return formatter.format(date);
    } catch (_err) {
      return date.toLocaleString('pt-BR', baseOptions);
    }
  }

  function attachCopyHandlers(container) {
    if (!container) {
      return;
    }

    container.querySelectorAll('.copy').forEach((anchor) => {
      anchor.onclick = async (event) => {
        event.preventDefault();
        const raw = anchor.getAttribute('data-copy') || anchor.textContent.trim();
        const text = anchor.dataset.copyType === 'cnpj' ? raw.replace(/\D+/g, '') : raw;
        try {
          await navigator.clipboard.writeText(text);
          if (anchor._copyTimer) {
            clearTimeout(anchor._copyTimer);
            anchor._copyTimer = null;
          }
          anchor.classList.remove('copied');
          const raf = window.requestAnimationFrame
            ? window.requestAnimationFrame.bind(window)
            : (fn) => setTimeout(fn, 0);
          raf(() => {
            anchor.classList.add('copied');
            anchor._copyTimer = setTimeout(() => {
              anchor.classList.remove('copied');
              anchor._copyTimer = null;
            }, 900);
          });
        } catch (error) {
          console.warn('Falha ao copiar item', error);
        }
      };
    });
  }

  function statusClass(status) {
    const key = (status || '').toLowerCase();
    if (key.includes('falha') || key.includes('erro')) return 'falha';
    if (key.includes('descart')) return 'descartado';
    if (key.includes('paus')) return 'pausado';
    return 'sucesso';
  }

  function normalizeText(value) {
    const str = String(value ?? '');
    if (typeof str.normalize === 'function') {
      return str
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .toLowerCase();
    }
    return str.toLowerCase();
  }

  function fmtLogDate(isoStr) {
    if (!isoStr) {
      return '';
    }
    return formatDateTime(isoStr, {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    });
  }

  function normEvent(event) {
    const etapaNome = event.etapa_nome || event.etapa || '';
    const created = event.created_at || event.timestamp || null;
    const contextoRaw = event.contexto || '';
    return {
      id: event.id || `${event.numero_plano || ''}|${event.status || ''}|${created || ''}|${etapaNome}`,
      contexto: contextoRaw || (etapaNome.startsWith('Tratamento') ? 'tratamento' : 'gestao'),
      etapa: etapaNome,
      etapa_numero: typeof event.etapa === 'number' ? event.etapa : event.etapa_numero ?? null,
      numero_plano: event.numero_plano || '',
      status: event.status || '',
      mensagem: event.mensagem || '',
      created_at: created,
    };
  }

  async function api(path, opts = {}) {
    const response = await fetch(path, {
      headers: {
        'Content-Type': 'application/json',
      },
      ...opts,
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    return response.json();
  }

  function downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  function formatLogStatus(status) {
    if (!status) {
      return '';
    }
    const map = {
      SUCESSO: 'Sucesso',
      INICIO: 'Início',
      DESCARTADO: 'Descartado',
      PAUSADO: 'Pausado',
      RETOMADO: 'Retomado',
      CONCLUIDO: 'Concluído',
      FALHA: 'Falha',
    };
    const upper = String(status).toUpperCase();
    if (map[upper]) {
      return map[upper];
    }
    return upper.charAt(0) + upper.slice(1).toLowerCase();
  }

  function toISODate(value) {
    return /^\d{4}-\d{2}-\d{2}$/.test(value) ? value : '';
  }

  function toBRFileDate(value) {
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value || '');
    return match ? `${match[3]}${match[2]}${match[1]}` : '';
  }

  global.SirepUtils = {
    $,
    fmtMoney,
    formatDateBR,
    formatDateTime,
    attachCopyHandlers,
    statusClass,
    normalizeText,
    fmtLogDate,
    normEvent,
    api,
    downloadBlob,
    formatLogStatus,
    toISODate,
    toBRFileDate,
    TIMEZONE,
  };
})(window);
