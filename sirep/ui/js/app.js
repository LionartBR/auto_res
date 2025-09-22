(function (global) {
  'use strict';

  const { elements: el, tabs, sections } = global.SirepDOM;
  const Gestao = global.SirepGestao;
  const Tratamento = global.SirepTratamento;
  const Logs = global.SirepLogs;

  let activeTab = null;

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

  document.addEventListener('DOMContentLoaded', () => {
    if (el.inputRescindidosData) {
      try {
        el.inputRescindidosData.value = new Date().toISOString().slice(0, 10);
      } catch (error) {
        console.warn('Falha ao definir data padrão', error);
      }
    }

    Logs.init();
    Gestao.init();
    Tratamento.init();
    initTabs();
    setActiveTab('gestao');
  });
})(window);
