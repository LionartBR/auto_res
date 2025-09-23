(function (global) {
  'use strict';

  const STORAGE_KEY = 'sirep:auth:v1';
  const ALGO_SHA256 = 'sha256';
  const ALGO_PLAIN = 'plain';
  const SALT_LENGTH = 16;

  let cachedCredentials = null;
  let warnedAboutFallback = false;

  function hasSecureCrypto() {
    return Boolean(
      global.crypto &&
      global.crypto.subtle &&
      typeof global.crypto.subtle.digest === 'function'
    );
  }

  function encodeUtf8(value) {
    const text = String(value ?? '');
    if (typeof TextEncoder === 'function') {
      return new TextEncoder().encode(text);
    }

    const encoded = encodeURIComponent(text);
    const parts = encoded.match(/%[0-9A-F]{2}|./gi) || [];
    const bytes = new Uint8Array(parts.length);
    for (let index = 0; index < parts.length; index += 1) {
      const part = parts[index];
      bytes[index] = part.startsWith('%') ? parseInt(part.slice(1), 16) : part.charCodeAt(0);
    }
    return bytes;
  }

  function bytesToBase64(bytes) {
    const buffer = bytes.buffer ? bytes.buffer : bytes;
    return bufferToBase64(buffer);
  }

  function getSaltBytes() {
    if (global.crypto && typeof global.crypto.getRandomValues === 'function') {
      return global.crypto.getRandomValues(new Uint8Array(SALT_LENGTH));
    }

    const salt = new Uint8Array(SALT_LENGTH);
    for (let index = 0; index < salt.length; index += 1) {
      salt[index] = Math.floor(Math.random() * 256);
    }
    return salt;
  }

  function emitFallbackWarning() {
    if (!warnedAboutFallback) {
      console.warn(
        'API de criptografia avançada indisponível; armazenando a senha utilizando codificação compatível.'
      );
      warnedAboutFallback = true;
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

  async function derivePasswordHash(password, saltBytes, algorithm) {
    const resolvedAlgorithm = algorithm || (hasSecureCrypto() ? ALGO_SHA256 : ALGO_PLAIN);

    if (resolvedAlgorithm === ALGO_SHA256) {
      if (!hasSecureCrypto()) {
        throw new Error('Algoritmo de hash seguro indisponível neste navegador.');
      }

      if (!saltBytes || !saltBytes.length) {
        throw new Error('Salt obrigatório para derivar hash seguro.');
      }

      const passwordBytes = encodeUtf8(password);
      const combined = new Uint8Array(saltBytes.length + passwordBytes.length);
      combined.set(saltBytes);
      combined.set(passwordBytes, saltBytes.length);
      const hashBuffer = await global.crypto.subtle.digest('SHA-256', combined);
      return bufferToBase64(hashBuffer);
    }

    if (resolvedAlgorithm === ALGO_PLAIN) {
      emitFallbackWarning();
      return bytesToBase64(encodeUtf8(password));
    }

    throw new Error(`Algoritmo de hash desconhecido: ${resolvedAlgorithm}`);
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
      cachedCredentials = {
        username: parsed.username,
        passwordHash: parsed.passwordHash,
        salt: typeof parsed.salt === 'string' ? parsed.salt : null,
        createdAt: typeof parsed.createdAt === 'string' ? parsed.createdAt : null,
        algorithm:
          typeof parsed.algorithm === 'string'
            ? parsed.algorithm
            : parsed.salt
              ? ALGO_SHA256
              : ALGO_PLAIN,
      };
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

    let saltBase64 = null;
    let passwordHash;
    let algorithm;

    if (hasSecureCrypto()) {
      const saltBytes = getSaltBytes();
      saltBase64 = bytesToBase64(saltBytes);
      passwordHash = await derivePasswordHash(password, saltBytes, ALGO_SHA256);
      algorithm = ALGO_SHA256;
    } else {
      passwordHash = await derivePasswordHash(password, null, ALGO_PLAIN);
      algorithm = ALGO_PLAIN;
    }

    const credentials = {
      username: safeUsername,
      passwordHash,
      createdAt: new Date().toISOString(),
      algorithm,
    };
    if (saltBase64) {
      credentials.salt = saltBase64;
    }
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
      const algorithm = credentials.algorithm || (credentials.salt ? ALGO_SHA256 : ALGO_PLAIN);
      const saltBytes = credentials.salt ? base64ToUint8Array(credentials.salt) : null;
      const checkHash = await derivePasswordHash(password, saltBytes, algorithm);
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
