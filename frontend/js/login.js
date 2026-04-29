(function () {
  const dot   = document.getElementById('esp-dot');
  const label = document.getElementById('esp-label');

  function setDot(online) {
    dot.classList.toggle('online', online);
    label.textContent = online ? 'ESP32 online' : 'ESP32 offline';
  }

  const poll = setInterval(async () => {
    try {
      const res  = await fetch(BASE_URL + '/auth/status?esp_id=ESP32_BAR_01');
      const data = await res.json();

      setDot(data.status !== 'esp_offline');

      if (data.status === 'authenticated') {
        clearInterval(poll);
        sessionStorage.setItem('token', data.token);
        sessionStorage.setItem('user',  JSON.stringify(data.user));
        window.location.href = '/select.html';
      }
    } catch {
      setDot(false);
    }
  }, 1000);
})();
