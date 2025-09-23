(function (global) {
  'use strict';

  const { $ } = global.SirepUtils;
  const Auth = global.SirepAuth;

  let overlay;
  let form;
  let userInput;
  let passwordInput;
  let feedback;
  let submitButton;
  let appShell;
  let onAuthenticatedCallback = null;

  function setFeedback(message) {
    if (!feedback) {
      return;
    }

    if (message) {
      feedback.textContent = message;
      feedback.hidden = false;
    } else {
      feedback.textContent = '';
      feedback.hidden = true;
    }
  }

  function disableForm(disabled) {
    if (submitButton) {
      submitButton.disabled = disabled;
    }
    if (userInput) {
      userInput.disabled = disabled;
    }
    if (passwordInput) {
      passwordInput.disabled = disabled;
    }
  }

  function hideOverlay() {
    if (!overlay) {
      return;
    }

    overlay.hidden = true;
    overlay.setAttribute('aria-hidden', 'true');
    setFeedback('');
    if (appShell) {
      appShell.hidden = false;
      appShell.removeAttribute('aria-hidden');
    }
  }

  function focusUsername() {
    if (userInput) {
      const focus = () => userInput.focus();
      if (global.requestAnimationFrame) {
        global.requestAnimationFrame(focus);
      } else {
        setTimeout(focus, 0);
      }
    }
  }

  function showOverlay() {
    if (!overlay) {
      return;
    }

    overlay.hidden = false;
    overlay.setAttribute('aria-hidden', 'false');
    disableForm(false);
    if (appShell) {
      appShell.hidden = true;
      appShell.setAttribute('aria-hidden', 'true');
    }
    focusUsername();
  }

  async function handleSubmit(event) {
    event.preventDefault();

    const username = userInput ? userInput.value : '';
    const password = passwordInput ? passwordInput.value : '';

    if (!username || !username.trim()) {
      setFeedback('Informe o usuário.');
      if (userInput) {
        userInput.focus();
      }
      return;
    }

    if (!password) {
      setFeedback('Informe a senha.');
      if (passwordInput) {
        passwordInput.focus();
      }
      return;
    }

    setFeedback('');
    disableForm(true);

    try {
      if (!Auth || typeof Auth.storeCredentials !== 'function') {
        throw new Error('Módulo de autenticação indisponível.');
      }
      await Auth.storeCredentials(username, password);
      if (form) {
        form.reset();
      }
      hideOverlay();
      if (typeof onAuthenticatedCallback === 'function') {
        onAuthenticatedCallback();
      }
    } catch (error) {
      console.error('Falha ao concluir o login.', error);
      const message = error && error.message ? String(error.message) : 'Não foi possível concluir o login. Tente novamente.';
      setFeedback(message);
      disableForm(false);
      if (passwordInput) {
        passwordInput.value = '';
        passwordInput.focus();
      }
      return;
    }

    disableForm(false);
    if (passwordInput) {
      passwordInput.value = '';
    }
  }

  function bindFieldListeners() {
    if (userInput) {
      userInput.addEventListener('input', () => {
        setFeedback('');
      });
    }

    if (passwordInput) {
      passwordInput.addEventListener('input', () => {
        setFeedback('');
      });
    }
  }

  function init(options) {
    overlay = $('#loginOverlay');
    form = $('#loginForm');
    userInput = $('#loginUser');
    passwordInput = $('#loginPassword');
    feedback = $('#loginError');
    submitButton = $('#loginSubmit');
    appShell = $('#appShell');

    onAuthenticatedCallback = options && typeof options.onAuthenticated === 'function' ? options.onAuthenticated : null;

    if (!Auth || typeof Auth.hasCredentials !== 'function') {
      console.error('Módulo de autenticação indisponível.');
      return;
    }

    if (!overlay || !form || !userInput || !passwordInput || !submitButton || !appShell) {
      console.warn('Componentes da tela de login não encontrados.');
      return;
    }

    form.addEventListener('submit', handleSubmit);
    bindFieldListeners();

    if (Auth && typeof Auth.getUsername === 'function' && userInput) {
      const storedUsername = Auth.getUsername();
      if (storedUsername) {
        userInput.value = storedUsername;
      }
    }

    showOverlay();
  }

  global.SirepLogin = {
    init,
    show: showOverlay,
    hide: hideOverlay,
  };
})(window);
