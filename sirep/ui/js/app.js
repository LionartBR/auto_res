(function (global) {
  'use strict';

  const { tabs, sections } = global.SirepDOM;
  const Gestao = global.SirepGestao;
  const Tratamento = global.SirepTratamento;
  const Logs = global.SirepLogs;
  const Login = global.SirepLogin;

  let activeTab = null;
  let bootstrapped = false;
  let appShell = null;

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

    if (Login && typeof Login.hide === 'function') {
      Login.hide();
    }

    Logs.init();
    Gestao.init();
    Tratamento.init();
    initTabs();
    setActiveTab('gestao');
  }

  document.addEventListener('DOMContentLoaded', () => {
    appShell = document.getElementById('appShell');

    if (Login && typeof Login.init === 'function') {
      Login.init({
        onAuthenticated: bootstrapApp,
      });
    }

  });
})(window);
