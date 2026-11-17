const assert = require('node:assert/strict');
const test = require('node:test');
const setupCoursePlayer = require('../code/site/course-player.js');

function createPlayer(ids) {
  const listeners = {};
  const buttons = ids.map((id, index) => {
    const rowClasses = new Set();
    const attributes = {};
    const events = {};
    return {
      dataset: { spotify: id, title: `Episode ${index + 1}` },
      events,
      attributes,
      rowClasses,
      addEventListener(name, callback) {
        events[name] = callback;
      },
      closest() {
        return { classList: { toggle: (name, active) => active ? rowClasses.add(name) : rowClasses.delete(name) } };
      },
      setAttribute(name, value) {
        attributes[name] = value;
      },
    };
  });
  const frame = {
    dataset: { spotify: ids[0] },
    src: `https://open.spotify.com/embed/episode/${ids[0]}`,
    title: 'Listen on Spotify: Episode 1',
  };
  const now = { textContent: 'Episode 1' };
  const calls = { loads: [], plays: 0 };
  const controller = {
    addListener(name, callback) {
      listeners[name] = callback;
    },
    loadEntity(uri) {
      calls.loads.push(uri);
    },
    play() {
      calls.plays += 1;
    },
  };
  const doc = {
    head: { appendChild() {} },
    getElementById: () => frame,
    querySelectorAll: () => buttons,
    querySelector: () => now,
    createElement: () => ({}),
  };
  const win = {};

  setupCoursePlayer(doc, win);
  win.onSpotifyIframeApiReady({
    createController(element, options, ready) {
      assert.equal(element, frame);
      assert.equal(options.uri, `spotify:episode:${ids[0]}`);
      ready(controller);
    },
  });

  return { buttons, calls, listeners, now };
}

test('selecting an episode updates selected state and starts it', () => {
  const { buttons, calls, now } = createPlayer(['first', 'second']);

  buttons[1].events.click();

  assert.equal(buttons[0].attributes['aria-pressed'], 'false');
  assert.equal(buttons[1].attributes['aria-pressed'], 'true');
  assert.equal(buttons[1].rowClasses.has('playing'), true);
  assert.equal(now.textContent, 'Episode 2');
  assert.deepEqual(calls.loads, ['spotify:episode:second']);
  assert.equal(calls.plays, 1);
});

test('episode completion advances once to the next episode', () => {
  const { calls, listeners } = createPlayer(['first', 'second', 'third']);

  listeners.playback_update({ data: {
    playingURI: 'spotify:episode:first',
    isPaused: true,
    isBuffering: false,
    position: 10000,
    duration: 10000,
  } });

  assert.deepEqual(calls.loads, ['spotify:episode:second']);
  assert.equal(calls.plays, 1);
});

test('a loaded next episode gets one play retry if it remains paused', () => {
  const { calls, listeners } = createPlayer(['first', 'second', 'third']);
  listeners.playback_update({ data: {
    playingURI: 'spotify:episode:first',
    isPaused: true,
    isBuffering: false,
    position: 10000,
    duration: 10000,
  } });
  assert.equal(calls.plays, 1);

  listeners.playback_update({ data: {
    playingURI: 'spotify:episode:second',
    isPaused: true,
    isBuffering: false,
    position: 0,
    duration: 20000,
  } });
  assert.equal(calls.plays, 2);

  listeners.playback_update({ data: {
    playingURI: 'spotify:episode:second',
    isPaused: true,
    isBuffering: false,
    position: 0,
    duration: 20000,
  } });
  assert.equal(calls.plays, 2);
});

test('a paused completion update just short of duration advances', () => {
  const { calls, listeners } = createPlayer(['first', 'second']);

  listeners.playback_update({ data: {
    playingURI: 'spotify:episode:first',
    isPaused: true,
    isBuffering: false,
    position: 99500,
    duration: 100000,
  } });

  assert.deepEqual(calls.loads, ['spotify:episode:second']);
  assert.equal(calls.plays, 1);
});

test('completion advances even when Spotify has not marked playback paused', () => {
  const { calls, listeners } = createPlayer(['first', 'second']);

  listeners.playback_update({ data: {
    playingURI: 'spotify:episode:first',
    isPaused: false,
    isBuffering: false,
    position: 100000,
    duration: 100000,
  } });

  assert.deepEqual(calls.loads, ['spotify:episode:second']);
  assert.equal(calls.plays, 1);
});

test('playback started in the embed synchronizes the selected episode', () => {
  const { buttons, listeners, now } = createPlayer(['first', 'second']);

  listeners.playback_started({ data: { playingURI: 'spotify:episode:second' } });

  assert.equal(buttons[0].attributes['aria-pressed'], 'false');
  assert.equal(buttons[1].attributes['aria-pressed'], 'true');
  assert.equal(buttons[1].rowClasses.has('playing'), true);
  assert.equal(now.textContent, 'Episode 2');
});

test('completion of the final episode does not advance past the playlist', () => {
  const { buttons, calls, listeners } = createPlayer(['first', 'last']);
  buttons[1].events.click();
  const loadsBeforeCompletion = calls.loads.length;
  const playsBeforeCompletion = calls.plays;

  listeners.playback_update({ data: {
    playingURI: 'spotify:episode:last',
    isPaused: true,
    isBuffering: false,
    position: 10000,
    duration: 10000,
  } });

  assert.equal(calls.loads.length, loadsBeforeCompletion);
  assert.equal(calls.plays, playsBeforeCompletion);
  assert.equal(buttons[1].attributes['aria-pressed'], 'true');
});

test('pausing before the end does not advance the playlist', () => {
  const { calls, listeners } = createPlayer(['first', 'second']);

  listeners.playback_update({ data: {
    playingURI: 'spotify:episode:first',
    isPaused: true,
    isBuffering: false,
    position: 8500,
    duration: 10000,
  } });

  assert.deepEqual(calls.loads, []);
});
