function setupCoursePlayer(doc, win) {
  const frame = doc.getElementById('course-player');
  if (!frame) return;

  const buttons = [...doc.querySelectorAll('.play[data-spotify]')];
  const now = doc.querySelector('.course-player .now b');
  let controller = null;
  let selectedId = frame.dataset.spotify;
  let advancedId = null;

  const mark = (id) => buttons.forEach((button) => {
    const active = button.dataset.spotify === id;
    button.setAttribute('aria-pressed', String(active));
    button.closest('li').classList.toggle('playing', active);
  });

  const select = (button) => {
    selectedId = button.dataset.spotify;
    advancedId = null;
    mark(selectedId);
    now.textContent = button.dataset.title;
    if (controller) {
      (controller.loadEntity || controller.loadUri)
        .call(controller, `spotify:episode:${selectedId}`, false, 0);
      controller.play();
    } else {
      frame.src = `https://open.spotify.com/embed/episode/${selectedId}`;
      frame.title = `${frame.title.split(':')[0]}: ${button.dataset.title}`;
    }
  };

  const syncPlayback = (uri) => {
    const id = typeof uri === 'string' ? uri.split(':').pop() : '';
    const button = buttons.find((candidate) => candidate.dataset.spotify === id);
    if (!button) return;
    selectedId = id;
    advancedId = null;
    mark(id);
    now.textContent = button.dataset.title;
  };

  buttons.forEach((button) => button.addEventListener('click', () => select(button)));

  win.onSpotifyIframeApiReady = (api) => api.createController(
    frame,
    { uri: `spotify:episode:${frame.dataset.spotify}`, width: '100%', height: 352 },
    (embed) => {
      controller = embed;
      controller.addListener('playback_started', (event) => {
        syncPlayback(event.data.playingURI);
      });
      controller.addListener('playback_update', (event) => {
        const state = event.data;
        if (state.playingURI !== `spotify:episode:${selectedId}`) return;
        if (!state.isPaused || state.isBuffering || state.duration <= 0 ||
            state.position < state.duration || advancedId === selectedId) return;

        const index = buttons.findIndex((button) => button.dataset.spotify === selectedId);
        advancedId = selectedId;
        if (index >= 0 && index < buttons.length - 1) select(buttons[index + 1]);
      });
    },
  );

  const apiScript = doc.createElement('script');
  apiScript.src = 'https://open.spotify.com/embed/iframe-api/v1';
  apiScript.async = true;
  doc.head.appendChild(apiScript);
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = setupCoursePlayer;
}

if (typeof document !== 'undefined' && typeof window !== 'undefined') {
  setupCoursePlayer(document, window);
}
