(function (global) {
  'use strict';

  const { tabs, sections } = global.SirepDOM;
  const Auth = global.SirepAuth;
  const Gestao = global.SirepGestao;
  const Tratamento = global.SirepTratamento;
  const Logs = global.SirepLogs;

  const DEFAULT_TAB = 'gestao';
  const VALID_TABS = ['gestao', 'tratamento'];

  let activeTab = null;
  let bootstrapped = false;
  let appShell = null;
  let logoutButton = null;

  const LOGIN_PAGE = 'login.html';

  function normalizeTab(name) {
    if (!name) {
      return null;
    }

    const normalized = String(name).trim().toLowerCase();
    return VALID_TABS.includes(normalized) ? normalized : null;
  }

  function getTabFromLocation() {
    const { location } = global;
    if (!location) {
      return null;
    }

    try {
      if (location.search) {
        const params = new URLSearchParams(location.search);
        const fromSearch = normalizeTab(params.get('tab'));
        if (fromSearch) {
          return fromSearch;
        }
      }

      if (location.hash) {
        const hashValue = location.hash.replace(/^#/u, '');
        const fromHash = normalizeTab(hashValue);
        if (fromHash) {
          return fromHash;
        }
      }
    } catch (error) {
      console.warn('Não foi possível interpretar o endereço para definir a aba inicial.', error);
    }

    return null;
  }

  function updateUrlForTab(name) {
    const tabName = normalizeTab(name);
    if (!tabName) {
      return;
    }

    const { history, location } = global;
    if (!location) {
      return;
    }

    try {
      const params = new URLSearchParams(location.search || '');
      params.set('tab', tabName);
      const search = params.toString();
      const hash = location.hash || '';
      const basePath = location.pathname || '';
      const newUrl = search ? `${basePath}?${search}${hash}` : `${basePath}${hash}`;

      if (history && typeof history.replaceState === 'function') {
        history.replaceState(null, '', newUrl);
      }
    } catch (error) {
      console.warn('Não foi possível atualizar o endereço da aba selecionada.', error);
    }
  }

  function getNextTargetForLogin() {
    const { location } = global;
    if (!location) {
      return null;
    }

    try {
      const pathname = location.pathname ? location.pathname.split('/').pop() || 'index.html' : 'index.html';
      const search = location.search || '';
      const hash = location.hash || '';
      const target = `${pathname}${search}${hash}`.trim();
      return target || null;
    } catch (error) {
      console.warn('Não foi possível compor o endereço de retorno após o login.', error);
      return null;
    }
  }

  function buildLoginUrl() {
    const nextTarget = getNextTargetForLogin();
    if (!nextTarget) {
      return LOGIN_PAGE;
    }

    const encodedNext = encodeURIComponent(nextTarget);
    const hasQuery = LOGIN_PAGE.includes('?');
    const separator = hasQuery ? '&' : '?';
    return `${LOGIN_PAGE}${separator}next=${encodedNext}`;
  }

  function updateTabDisplay(name) {
    tabs.forEach((tab) => {
      tab.classList.toggle('active', tab.dataset.tab === name);
    });

    sections.forEach((section) => {
      section.style.display = section.id === `tab-${name}` ? 'block' : 'none';
    });
  }

  function setActiveTab(name, options) {
    const tabName = normalizeTab(name);
    if (!tabName || activeTab === tabName) {
      return;
    }

    activeTab = tabName;
    updateTabDisplay(tabName);

    if (tabName === 'gestao') {
      Tratamento.deactivate();
      Promise.resolve(Gestao.activate()).catch((error) => {
        console.error('Falha ao ativar aba Gestão', error);
      });
    } else if (tabName === 'tratamento') {
      Gestao.deactivate();
      Promise.resolve(Tratamento.activate()).catch((error) => {
        console.error('Falha ao ativar aba Tratamento', error);
      });
    }

    if (!options || options.updateUrl !== false) {
      updateUrlForTab(tabName);
    }
  }

  function initTabs() {
    tabs.forEach((tab) => {
      tab.addEventListener('click', (event) => {
        event.preventDefault();
        const target = tab.dataset.tab;
        if (target) {
          setActiveTab(target);
        }
      });
    });
  }

  function bootstrapApp() {
    if (bootstrapped) {
      return;
    }

    bootstrapped = true;

    if (!appShell) {
      appShell = document.getElementById('appShell');
    }

    if (appShell) {
      appShell.hidden = false;
      appShell.removeAttribute('aria-hidden');
    }

    Logs.init();
    Gestao.init();
    Tratamento.init();
    initTabs();

    const initialTab = getTabFromLocation();
    if (initialTab) {
      setActiveTab(initialTab);
    } else {
      setActiveTab(DEFAULT_TAB, { updateUrl: false });
    }
  }

  function handleLogout() {
    if (Auth && typeof Auth.clearCredentials === 'function') {
      try {
        Auth.clearCredentials();
      } catch (error) {
        console.warn('Falha ao limpar credenciais ao encerrar sessão.', error);
      }
    }

    if (appShell) {
      appShell.setAttribute('aria-hidden', 'true');
      appShell.hidden = true;
    }

    redirectToLogin();
  }

  function redirectToLogin() {
    const loginUrl = buildLoginUrl();

    if (global.location && typeof global.location.replace === 'function') {
      global.location.replace(loginUrl);
    } else {
      global.location.href = loginUrl;
    }
  }

  function ensureAuthenticated() {
    if (!Auth || typeof Auth.hasCredentials !== 'function') {
      return true;
    }

    try {
      if (Auth.hasCredentials()) {
        return true;
      }
    } catch (error) {
      console.warn('Não foi possível verificar as credenciais armazenadas.', error);
    }

    redirectToLogin();
    return false;
  }

  document.addEventListener('DOMContentLoaded', () => {
    appShell = document.getElementById('appShell');
    logoutButton = document.getElementById('logoutButton');

    if (logoutButton) {
      logoutButton.addEventListener('click', (event) => {
        event.preventDefault();
        handleLogout();
      });
    }

    if (ensureAuthenticated()) {
      bootstrapApp();
    }

  });
})(window);
