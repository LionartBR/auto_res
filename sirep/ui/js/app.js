(function (global) {
  'use strict';

  const { tabs, sections } = global.SirepDOM;
  const Auth = global.SirepAuth;
  const Gestao = global.SirepGestao;
  const Tratamento = global.SirepTratamento;
  const Logs = global.SirepLogs;

  let activeTab = null;
  let bootstrapped = false;
  let appShell = null;
  let logoutButton = null;

  const LOGIN_PAGE = 'login.html';

  function updateTabDisplay(name) {
    tabs.forEach((tab) => {
      tab.classList.toggle('active', tab.dataset.tab === name);
    });

    sections.forEach((section) => {
      section.style.display = section.id === `tab-${name}` ? 'block' : 'none';
    });
  }

  function setActiveTab(name) {
    if (!name || activeTab === name) {
      return;
    }

    activeTab = name;
    updateTabDisplay(name);

    if (name === 'gestao') {
      Tratamento.deactivate();
      Promise.resolve(Gestao.activate()).catch((error) => {
        console.error('Falha ao ativar aba Gestão', error);
      });
    } else if (name === 'tratamento') {
      Gestao.deactivate();
      Promise.resolve(Tratamento.activate()).catch((error) => {
        console.error('Falha ao ativar aba Tratamento', error);
      });
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
    setActiveTab('gestao');
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
    if (global.location && typeof global.location.replace === 'function') {
      global.location.replace(LOGIN_PAGE);
    } else {
      global.location.href = LOGIN_PAGE;
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
