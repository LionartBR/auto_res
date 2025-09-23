(function (global) {
  'use strict';

  const STORAGE_KEY = 'sirep:auth:v1';

  let cachedCredentials = null;

  function ensureCrypto() {
    if (!global.crypto || !global.crypto.subtle) {
      throw new Error('O navegador não suporta a API de criptografia necessária.');
    }
  }

  function bufferToBase64(buffer) {
    const bytes = new Uint8Array(buffer);
    let binary = '';
    bytes.forEach((byte) => {
      binary += String.fromCharCode(byte);
    });
    return global.btoa(binary);
  }

  function base64ToUint8Array(base64) {
    const binary = global.atob(base64);
    const bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index += 1) {
      bytes[index] = binary.charCodeAt(index);
    }
    return bytes;
  }

  async function derivePasswordHash(password, saltBytes) {
    ensureCrypto();
    const encoder = new TextEncoder();
    const passwordBytes = encoder.encode(password);
    const combined = new Uint8Array(saltBytes.length + passwordBytes.length);
    combined.set(saltBytes);
    combined.set(passwordBytes, saltBytes.length);
    const hashBuffer = await global.crypto.subtle.digest('SHA-256', combined);
    return bufferToBase64(hashBuffer);
  }

  function persist(credentials) {
    const payload = { ...credentials };
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
    } catch (error) {
      console.error('Não foi possível armazenar as credenciais na sessão com segurança.', error);
      throw new Error('Falha ao armazenar as credenciais com segurança.');
    }
    cachedCredentials = payload;
  }

  function loadFromStorage() {
    if (cachedCredentials) {
      return cachedCredentials;
    }

    let stored;
    try {
      stored = sessionStorage.getItem(STORAGE_KEY);
    } catch (error) {
      console.warn('Não foi possível acessar o armazenamento seguro de credenciais.', error);
      cachedCredentials = null;
      return null;
    }
    if (!stored) {
      return null;
    }

    try {
      const parsed = JSON.parse(stored);
      if (!parsed || typeof parsed.username !== 'string' || typeof parsed.passwordHash !== 'string') {
        throw new Error('Formato inválido.');
      }
      cachedCredentials = { ...parsed };
      return cachedCredentials;
    } catch (error) {
      console.warn('Não foi possível carregar as credenciais armazenadas com segurança.', error);
      sessionStorage.removeItem(STORAGE_KEY);
      cachedCredentials = null;
      return null;
    }
  }

  async function storeCredentials(username, password) {
    const safeUsername = String(username || '').trim();
    if (!safeUsername) {
      throw new Error('Usuário obrigatório.');
    }

    if (!password) {
      throw new Error('Senha obrigatória.');
    }

    ensureCrypto();
    const saltBytes = global.crypto.getRandomValues(new Uint8Array(16));
    const passwordHash = await derivePasswordHash(password, saltBytes);
    const credentials = {
      username: safeUsername,
      salt: bufferToBase64(saltBytes),
      passwordHash,
      createdAt: new Date().toISOString(),
    };
    persist(credentials);
    return getCredentials();
  }

  function clearCredentials() {
    sessionStorage.removeItem(STORAGE_KEY);
    cachedCredentials = null;
  }

  function hasCredentials() {
    return Boolean(loadFromStorage());
  }

  function getCredentials() {
    const stored = loadFromStorage();
    return stored ? { ...stored } : null;
  }

  function getPasswordHash() {
    const credentials = loadFromStorage();
    return credentials ? credentials.passwordHash : null;
  }

  function getUsername() {
    const credentials = loadFromStorage();
    return credentials ? credentials.username : null;
  }

  async function verifyPassword(password) {
    const credentials = loadFromStorage();
    if (!credentials || !password) {
      return false;
    }

    try {
      if (!credentials.salt) {
        return false;
      }
      const saltBytes = base64ToUint8Array(credentials.salt);
      const checkHash = await derivePasswordHash(password, saltBytes);
      return checkHash === credentials.passwordHash;
    } catch (error) {
      console.warn('Falha ao verificar a senha fornecida.', error);
      return false;
    }
  }

  global.SirepAuth = {
    storeCredentials,
    hasCredentials,
    getCredentials,
    getPasswordHash,
    getUsername,
    verifyPassword,
    clearCredentials,
  };
})(window);
