"""Static website for Repeto.stream: homepage, course pages and printable transcripts."""

from __future__ import annotations

import hashlib
import html
import json
import random
import re
import shutil
from pathlib import Path
from urllib.parse import urlparse

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from markupsafe import Markup

ROOT = Path(__file__).resolve().parent.parent
BRAND = 'Repeto.stream'
GITHUB_URL = 'https://github.com/trusohamn/repeto'
EMAIL = 'repeto.stream@gmail.com'

ORDER = ['sv', 'pl', 'en', 'ru', 'es', 'de', 'fr']
NATIVE = {
    'sv': 'Svenska', 'pl': 'Polski', 'en': 'English', 'ru': 'Русский',
    'es': 'Español', 'de': 'Deutsch', 'fr': 'Français',
}
NAMES = {
    'en': {'sv': 'Swedish', 'pl': 'Polish', 'en': 'English', 'ru': 'Russian', 'es': 'Spanish', 'de': 'German', 'fr': 'French'},
    'sv': {'sv': 'Svenska', 'pl': 'Polska', 'en': 'Engelska', 'ru': 'Ryska', 'es': 'Spanska', 'de': 'Tyska', 'fr': 'Franska'},
    'pl': {'sv': 'Szwedzki', 'pl': 'Polski', 'en': 'Angielski', 'ru': 'Rosyjski', 'es': 'Hiszpański', 'de': 'Niemiecki', 'fr': 'Francuski'},
    'ru': {'sv': 'Шведский', 'pl': 'Польский', 'en': 'Английский', 'ru': 'Русский', 'es': 'Испанский', 'de': 'Немецкий', 'fr': 'Французский'},
    'es': {'sv': 'Sueco', 'pl': 'Polaco', 'en': 'Inglés', 'ru': 'Ruso', 'es': 'Español', 'de': 'Alemán', 'fr': 'Francés'},
}
PRACTICE_KEY = {'sv': 'se'}

# Course picker sentence: "<speak> [language] <learn> [language]", in the speaker's language.
PICKER = {
    'en': {'speak': 'I speak', 'learn': 'and want to learn', 'start': 'Start listening', 'self': 'English',
           'targets': {k: v for k, v in NAMES['en'].items()}},
    'sv': {'speak': 'Jag talar', 'learn': 'och vill lära mig', 'start': 'Börja lyssna', 'self': 'svenska',
           'targets': {k: v.lower() for k, v in NAMES['sv'].items()}},
    'pl': {'speak': 'Mówię', 'learn': 'i chcę się uczyć', 'start': 'Zacznij słuchać', 'self': 'po polsku',
           'targets': {'sv': 'szwedzkiego', 'pl': 'polskiego', 'en': 'angielskiego', 'ru': 'rosyjskiego',
                       'es': 'hiszpańskiego', 'de': 'niemieckiego', 'fr': 'francuskiego'}},
    'ru': {'speak': 'Я говорю', 'learn': 'и хочу учить', 'start': 'Начать слушать', 'self': 'по-русски',
           'targets': {k: v.lower() for k, v in NAMES['ru'].items()}},
    'es': {'speak': 'Hablo', 'learn': 'y quiero aprender', 'start': 'Empezar a escuchar', 'self': 'español',
           'targets': {k: v.lower() for k, v in NAMES['es'].items()}},
}

UI = {
    'en': {
        'all_episodes': 'All episodes and transcripts', 'no_transcript': 'There is no transcript for this episode yet.',
        'skip': 'Skip to content', 'all_courses': 'All courses',
        'episodes': ('episode', 'episodes'), 'topics': ('practice topic', 'practice topics'),
        'chapters': ('story chapter', 'story chapters'), 'phrases': ('phrase', 'phrases'), 'listening': 'of listening',
        'hm': '{h} h {m} min', 'min': 'min',
        'spotify': 'Listen on Spotify', 'youtube': 'Listen on YouTube', 'transcripts': 'Printable transcripts',
        'soon_spotify': 'This course is coming to Spotify soon.',
        'how': 'How to listen',
        'steps': [
            ('Press play', 'Start with episode 1 and put the screen away.'),
            ('Say it out loud', 'You hear a phrase in your language. Say it in the new language during the pause.'),
            ('Listen and repeat', 'The answer is played twice. Say it along with the voice.'),
        ],
        'about': 'About this course', 'kind_story': 'Story', 'episode': 'Episode', 'transcript': 'Transcript',
        'print_season': 'Print all transcripts', 'print': 'Print', 'back': 'Back to the course',
        'hear': 'You hear', 'say': 'You say',
        'practice_intro': 'You hear the left column. Say the right column out loud in the pause – then the answer is played twice.',
        'part1': 'Part 1 · Listen to the chapter', 'part2': 'Part 2 · Practise the words',
        'part3': 'Part 3 · Listen to the chapter again',
        'again': 'The same text is read again.',
        'translation': 'Translation', 'mistake': 'Spotted a mistake?',
        'mistake_text': 'Soon you will be able to suggest a correction right here.', 'soon': 'Coming soon',
        'until': 'Until then, write to us:', 'open_source': 'Repeto.stream is free and open source.',
        'voices': 'AI-generated voices (Microsoft Azure).',
    },
    'sv': {
        'all_episodes': 'Alla avsnitt och transkript', 'no_transcript': 'Det finns inget transkript för det här avsnittet än.',
        'skip': 'Hoppa till innehållet', 'all_courses': 'Alla kurser',
        'episodes': ('avsnitt', 'avsnitt'), 'topics': ('övningsämne', 'övningsämnen'),
        'chapters': ('berättelsekapitel', 'berättelsekapitel'), 'phrases': ('fras', 'fraser'), 'listening': 'lyssning',
        'hm': '{h} tim {m} min', 'min': 'min',
        'spotify': 'Lyssna på Spotify', 'youtube': 'Lyssna på YouTube', 'transcripts': 'Utskrivbara transkript',
        'soon_spotify': 'Kursen kommer snart till Spotify.',
        'how': 'Så lyssnar du',
        'steps': [
            ('Tryck på play', 'Börja med avsnitt 1 och lägg undan skärmen.'),
            ('Säg det högt', 'Du hör en fras på ditt språk. Säg den på det nya språket i pausen.'),
            ('Lyssna och härma', 'Svaret spelas två gånger. Säg det igen tillsammans med rösten.'),
        ],
        'about': 'Om kursen', 'kind_story': 'Berättelse', 'episode': 'Avsnitt', 'transcript': 'Transkript',
        'print_season': 'Skriv ut alla transkript', 'print': 'Skriv ut', 'back': 'Tillbaka till kursen',
        'hear': 'Du hör', 'say': 'Du säger',
        'practice_intro': 'Du hör vänster kolumn. Säg höger kolumn högt i pausen – sedan spelas svaret två gånger.',
        'part1': 'Del 1 · Lyssna på kapitlet', 'part2': 'Del 2 · Öva orden',
        'part3': 'Del 3 · Lyssna på kapitlet igen',
        'again': 'Samma text läses igen.',
        'translation': 'Översättning', 'mistake': 'Hittat ett fel?',
        'mistake_text': 'Snart kan du föreslå en rättelse direkt här.', 'soon': 'Kommer snart',
        'until': 'Till dess, skriv till oss:', 'open_source': 'Repeto.stream är gratis och har öppen källkod.',
        'voices': 'AI-genererade röster (Microsoft Azure).',
    },
    'pl': {
        'all_episodes': 'Wszystkie odcinki i transkrypcje', 'no_transcript': 'Ten odcinek nie ma jeszcze transkrypcji.',
        'skip': 'Przejdź do treści', 'all_courses': 'Wszystkie kursy',
        'episodes': ('odcinek', 'odcinki', 'odcinków'), 'topics': ('temat ćwiczeń', 'tematy ćwiczeń', 'tematów ćwiczeń'),
        'chapters': ('rozdział opowieści', 'rozdziały opowieści', 'rozdziałów opowieści'), 'phrases': ('fraza', 'frazy', 'fraz'), 'listening': 'słuchania',
        'hm': '{h} godz. {m} min', 'min': 'min',
        'spotify': 'Słuchaj na Spotify', 'youtube': 'Słuchaj na YouTube', 'transcripts': 'Transkrypcje do druku',
        'soon_spotify': 'Ten kurs wkrótce pojawi się na Spotify.',
        'how': 'Jak słuchać',
        'steps': [
            ('Naciśnij play', 'Zacznij od odcinka 1 i odłóż ekran.'),
            ('Powiedz to na głos', 'Słyszysz zdanie w swoim języku. W pauzie powiedz je w nowym języku.'),
            ('Słuchaj i powtarzaj', 'Odpowiedź pada dwa razy. Powtórz ją razem z lektorem.'),
        ],
        'about': 'O kursie', 'kind_story': 'Opowieść', 'episode': 'Odcinek', 'transcript': 'Transkrypcja',
        'print_season': 'Wydrukuj wszystkie transkrypcje', 'print': 'Drukuj', 'back': 'Wróć do kursu',
        'hear': 'Słyszysz', 'say': 'Mówisz',
        'practice_intro': 'Słyszysz lewą kolumnę. W pauzie powiedz na głos prawą – potem odpowiedź zabrzmi dwa razy.',
        'part1': 'Część 1 · Posłuchaj rozdziału', 'part2': 'Część 2 · Ćwicz słowa',
        'part3': 'Część 3 · Posłuchaj rozdziału jeszcze raz',
        'again': 'Ten sam tekst czytany jest ponownie.',
        'translation': 'Tłumaczenie', 'mistake': 'Widzisz błąd?',
        'mistake_text': 'Wkrótce zaproponujesz poprawkę bezpośrednio tutaj.', 'soon': 'Wkrótce',
        'until': 'Do tego czasu napisz do nas:', 'open_source': 'Repeto.stream jest darmowe i ma otwarty kod źródłowy.',
        'voices': 'Głosy wygenerowane przez AI (Microsoft Azure).',
    },
    'ru': {
        'all_episodes': 'Все эпизоды и тексты', 'no_transcript': 'Для этого эпизода текста пока нет.',
        'skip': 'Перейти к содержанию', 'all_courses': 'Все курсы',
        'episodes': ('эпизод', 'эпизода', 'эпизодов'), 'topics': ('тема для практики', 'темы для практики', 'тем для практики'),
        'chapters': ('глава истории', 'главы истории', 'глав истории'), 'phrases': ('фраза', 'фразы', 'фраз'), 'listening': 'прослушивания',
        'hm': '{h} ч {m} мин', 'min': 'мин',
        'spotify': 'Слушать в Spotify', 'youtube': 'Слушать на YouTube', 'transcripts': 'Тексты для печати',
        'soon_spotify': 'Скоро этот курс появится в Spotify.',
        'how': 'Как слушать',
        'steps': [
            ('Нажмите play', 'Начните с первого эпизода и отложите экран.'),
            ('Скажите вслух', 'Вы слышите фразу на своём языке. В паузе скажите её на новом языке.'),
            ('Слушайте и повторяйте', 'Ответ звучит дважды. Повторите его вместе с диктором.'),
        ],
        'about': 'О курсе', 'kind_story': 'История', 'episode': 'Эпизод', 'transcript': 'Текст',
        'print_season': 'Распечатать все тексты', 'print': 'Распечатать', 'back': 'Назад к курсу',
        'hear': 'Вы слышите', 'say': 'Вы говорите',
        'practice_intro': 'Вы слышите левую колонку. В паузе скажите вслух правую – затем ответ прозвучит дважды.',
        'part1': 'Часть 1 · Слушайте главу', 'part2': 'Часть 2 · Тренируйте слова',
        'part3': 'Часть 3 · Послушайте главу ещё раз',
        'again': 'Тот же текст звучит ещё раз.',
        'translation': 'Перевод', 'mistake': 'Нашли ошибку?',
        'mistake_text': 'Скоро здесь можно будет предложить исправление.', 'soon': 'Скоро',
        'until': 'А пока напишите нам:', 'open_source': 'Repeto.stream — бесплатный проект с открытым исходным кодом.',
        'voices': 'Голоса созданы ИИ (Microsoft Azure).',
    },
    'es': {
        'all_episodes': 'Todos los episodios y transcripciones', 'no_transcript': 'Este episodio todavía no tiene transcripción.',
        'skip': 'Saltar al contenido', 'all_courses': 'Todos los cursos',
        'episodes': ('episodio', 'episodios'), 'topics': ('tema de práctica', 'temas de práctica'),
        'chapters': ('capítulo del cuento', 'capítulos del cuento'), 'phrases': ('frase', 'frases'), 'listening': 'de escucha',
        'hm': '{h} h {m} min', 'min': 'min',
        'spotify': 'Escuchar en Spotify', 'youtube': 'Escuchar en YouTube', 'transcripts': 'Transcripciones para imprimir',
        'soon_spotify': 'Este curso llegará pronto a Spotify.',
        'how': 'Cómo escuchar',
        'steps': [
            ('Dale al play', 'Empieza por el episodio 1 y aparta la pantalla.'),
            ('Dilo en voz alta', 'Oyes una frase en tu idioma. Dila en el nuevo idioma durante la pausa.'),
            ('Escucha y repite', 'La respuesta suena dos veces. Repítela junto con la voz.'),
        ],
        'about': 'Sobre el curso', 'kind_story': 'Historia', 'episode': 'Episodio', 'transcript': 'Transcripción',
        'print_season': 'Imprimir todas las transcripciones', 'print': 'Imprimir', 'back': 'Volver al curso',
        'hear': 'Oyes', 'say': 'Dices',
        'practice_intro': 'Oyes la columna de la izquierda. Di en voz alta la de la derecha durante la pausa; después la respuesta suena dos veces.',
        'part1': 'Parte 1 · Escucha el capítulo', 'part2': 'Parte 2 · Practica las palabras',
        'part3': 'Parte 3 · Escucha el capítulo otra vez',
        'again': 'Se lee el mismo texto otra vez.',
        'translation': 'Traducción', 'mistake': '¿Has visto un error?',
        'mistake_text': 'Pronto podrás sugerir una corrección aquí mismo.', 'soon': 'Próximamente',
        'until': 'Mientras tanto, escríbenos:', 'open_source': 'Repeto.stream es gratuito y de código abierto.',
        'voices': 'Voces generadas por IA (Microsoft Azure).',
    },
}

PRACTICE_ID = re.compile(r'^repeto:[^:]+:topic-(\d+)$')
STORY_ID = re.compile(r'^([a-z0-9_]+):([a-z]{2}):([a-z]{2}):chapter-(\d+)$')
LIST_ITEM = re.compile(r'(?:•|\d+\.)\s+')
SPOTIFY_SHOW = re.compile(r'^https://open\.spotify\.com/show/([A-Za-z0-9]{22})$')

e = html.escape


def text_to_html(text: str) -> str:
    """Render plain description text: blank lines split paragraphs, • or N. lines form lists."""
    blocks = []
    for paragraph in text.strip().split('\n\n'):
        lines = paragraph.splitlines()
        heading = [line for line in lines if not LIST_ITEM.match(line)]
        items = [LIST_ITEM.sub('', line, count=1) for line in lines if LIST_ITEM.match(line)]
        if heading and not items:
            blocks.append('<p>' + '<br>'.join(e(line) for line in lines) + '</p>')
            continue
        if heading:
            blocks.append('<p>' + '<br>'.join(e(line) for line in heading) + '</p>')
        tag = 'ol' if LIST_ITEM.match(lines[-1]) and lines[-1][0].isdigit() else 'ul'
        blocks.append(f'<{tag}>' + ''.join(f'<li>{e(item)}</li>' for item in items) + f'</{tag}>')
    return ''.join(blocks)


def plural(ui: str, n: int, key: str) -> str:
    forms = UI[ui][key]
    if len(forms) == 2:
        return forms[0] if n == 1 else forms[1]
    if n % 10 == 1 and n % 100 != 11:
        return forms[0]
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return forms[1]
    return forms[2]


def hours(ui: str, ms: int) -> str:
    minutes = round(ms / 60000)
    return UI[ui]['hm'].format(h=minutes // 60, m=minutes % 60)


def minutes(ui: str, ms: int) -> str:
    return f'{max(1, round(ms / 60000))} {UI[ui]["min"]}'


def short_title(title: str) -> str:
    for separator in (' – ', ': ', ' - '):
        if title.startswith(BRAND + separator):
            return title[len(BRAND + separator):]
    return title


def first_paragraph(text: str) -> str:
    return text.strip().split('\n\n', 1)[0].strip()


# ---------------------------------------------------------------------------
# Transcript data


def load_practice(path: Path | None = None) -> dict:
    """Return topics in course order: [{'topic': name, 'phrases': [{lang: text}]}]."""
    rows = json.loads((path or ROOT / 'courses/practice/transcript.json').read_text(encoding='utf-8'))
    topics: dict[str, list[dict]] = {}
    for row in rows:
        topics.setdefault(row['topic'], []).append(row)
    names_path = (path.parent if path else ROOT / 'courses/practice') / 'topics.json'
    names = json.loads(names_path.read_text(encoding='utf-8')) if names_path.exists() else {}
    return {'topics': [{'topic': topic, 'names': names.get(topic, {}), 'phrases': phrases} for topic, phrases in topics.items()]}


def load_story(story: str) -> dict | None:
    path = ROOT / 'courses/stories' / story / 'generated/transcript.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else None


def practice_text(row: dict, lang: str) -> str:
    return row.get(PRACTICE_KEY.get(lang, lang)) or row.get(lang, '')


def topic_name(topic: dict, lang: str) -> str:
    names = topic['names']
    return names.get(PRACTICE_KEY.get(lang, lang)) or names.get(lang) or topic['topic']


def story_vocabulary_order(chapter: dict) -> list[dict]:
    """Vocabulary in the order it is spoken (mirrors the shuffle in story_course.py)."""
    vocabulary = list(chapter['vocabulary'])
    random.Random(f'{chapter["chapter_number"]}:{chapter["titles"]["pl"]}').shuffle(vocabulary)
    return vocabulary


# ---------------------------------------------------------------------------
# Rendering

TEMPLATES = Path(__file__).resolve().parent / 'templates'
ASSETS = Path(__file__).resolve().parent / 'site'
ENV = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=True, trim_blocks=True, lstrip_blocks=True,
                  keep_trailing_newline=True, undefined=StrictUndefined)
ENV.globals.update(BRAND=BRAND, GITHUB_URL=GITHUB_URL, EMAIL=EMAIL)


def write_assets(root: Path) -> dict[str, str]:
    """Copy site.css/site.js to podcast/assets/ with a content hash in the name; return {kind: relative url}."""
    folder = root / 'assets'
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir()
    urls = {}
    for kind in ('css', 'js'):
        data = (ASSETS / f'site.{kind}').read_bytes()
        name = f'site-{hashlib.sha256(data).hexdigest()[:10]}.{kind}'
        (folder / name).write_bytes(data)
        urls[kind] = f'assets/{name}'
    return urls


def render(template: str, *, assets: dict, title: str, lang: str, prefix: str, description: str, canonical: str,
           image: str | None, ui: str = 'en', **context) -> str:
    return ENV.get_template(template).render(
        assets=assets, title=title, lang=lang, prefix=prefix, description=description, canonical=canonical,
        image=image, t=UI[ui], **context)


# ---------------------------------------------------------------------------
# Homepage

WORD_PAIRS = [('Hej!', '¡Hola!'), ('Cześć!', 'Hello!'), ('Привет!', 'Hej!'), ('Hello!', 'Bonjour!'), ('¡Hola!', 'Hallo!')]

MOMENTS = ['Walking to school', 'Car rides', 'Cooking together', 'Quiet play', 'On the bus',
           'Doing chores', 'Winding down', 'Out for a run', 'Travelling']

STEPS = [
    ('step-1-pick.jpg', 'Pick a course', 'Choose the language you speak and the one you want to learn.'),
    ('step-2-play.jpg', 'Press play', "Start with episode 1. You don't need to look at the screen after that."),
    ('step-3-say.jpg', 'Say it', 'You hear a phrase in your language. Say it in the new language during the pause.'),
    ('step-4-repeat.jpg', 'Check and repeat', 'The answer is played twice. Check what you said and say it again.'),
]

AUDIENCE = [
    ('family-1-screen-free.jpg', 'Screen-free', 'Nothing to look at, so you can listen while walking, driving or cooking.'),
    ('family-2-free.jpg', 'Free, no ads', 'No account, no tracking on this site, nothing to pay for.'),
    ('family-3-print.jpg', 'Printable transcripts', 'Every episode has a transcript you can read or print.'),
    ('family-4-beginner.jpg', 'Beginner-friendly', 'Starts from zero and repeats each phrase several times. No reading needed.'),
]

PLANNED = [
    ('soon-correction.jpg', 'Suggest a correction', 'Found a mistake in a phrase? You will be able to report it from the transcript page.'),
    ('soon-request.jpg', 'Request a language', 'You will be able to vote for the next language pair.'),
]


def course_counts(course: dict) -> dict:
    episodes = course['episodes']
    seasons = {str(k): [ep for ep in episodes if str(ep.get('season')) == str(k)] for k in course.get('seasons', {})}
    return {
        'episodes': len(episodes),
        'practice': len(seasons.get('1', [])),
        'story': len(seasons.get('2', [])),
        'ms': sum(int(ep.get('duration_ms') or 0) for ep in episodes),
    }


def episode_meta(course: dict, ui: str) -> str:
    counts = course_counts(course)
    return f'{counts["episodes"]} {plural(ui, counts["episodes"], "episodes")} · {hours(ui, counts["ms"])}'


def build_home(courses: list[dict], base_url: str, assets: dict) -> str:
    by_source: dict[str, list[dict]] = {}
    for course in courses:
        by_source.setdefault(course['source_language'], []).append(course)
    for group in by_source.values():
        group.sort(key=lambda c: ORDER.index(c['target_language']))
    sources = sorted(by_source, key=ORDER.index)
    groups = [{
        'source': source, 'native': NATIVE[source], 'name': NAMES['en'][source],
        'cards': [{
            'slug': c['slug'], 'cover': c['cover'], 'target': c['target_language'],
            'pair': f'{NAMES["en"][source]} → {NAMES["en"][c["target_language"]]}',
            'title': short_title(c['title']), 'meta': episode_meta(c, 'en'),
            'spotify': 'Spotify' in c.get('links', {}),
        } for c in by_source[source]],
    } for source in sources]
    picker_data = {}
    for source in sources:
        words = PICKER[source]
        picker_data[source] = {
            'speak': words['speak'], 'learn': words['learn'], 'start': words['start'],
            'courses': [{
                'target': c['target_language'], 'name': words['targets'][c['target_language']],
                'href': f'{c["slug"]}/', 'cover': f'{c["slug"]}/{c["cover"]}', 'title': short_title(c['title']),
                'pair': f'{NAMES[source][source]} → {NAMES[source][c["target_language"]]}',
                'meta': episode_meta(c, source),
            } for c in by_source[source]],
        }
    default = 'en' if 'en' in by_source else sources[0]
    picker = {
        'source': default, 'first': picker_data[default], 'course': picker_data[default]['courses'][0],
        'speak_options': [(s, PICKER[s]['self']) for s in sources],
        'json': Markup(json.dumps(picker_data, ensure_ascii=False).replace('</', '<\\/')),
    }
    total = len(courses)
    return render(
        'home.html', assets=assets, title=f'{BRAND} – screen-free language learning on the go', lang='en', prefix='',
        description=f'Free audio language courses for children and adults. {total} language pairs.',
        canonical=f'{base_url}/', image=f'{base_url}/social.jpeg',
        total=total, groups=groups, picker=picker, word_pairs=WORD_PAIRS, moments=MOMENTS,
        steps=STEPS, audience=AUDIENCE, planned=PLANNED,
        story_cover=next((c['story_cover'] for c in courses if c.get('story_cover')), None),
    )


# ---------------------------------------------------------------------------
# Course pages


def transcript_name(episode: dict) -> str:
    return f'season-{episode["season"]}-episode-{int(episode["episode"]):02d}.html'


def episode_url(base_url: str, slug: str, episode: dict) -> str:
    """Public URL of an episode page (also used as the feed item <link>)."""
    return f'{base_url.rstrip("/")}/{slug}/transcripts/{transcript_name(episode)}'


def course_ui(course: dict) -> str:
    source = course.get('source_language') or course.get('language')
    return source if source in UI else 'en'


def season_name(season: str) -> str:
    return f'season-{season}.html'


def season_episodes(course: dict, season) -> list[dict]:
    return sorted((ep for ep in course['episodes'] if str(ep.get('season')) == str(season)), key=lambda ep: int(ep['episode']))


def course_page(course: dict, base_url: str, assets: dict) -> str:
    ui = course['ui']
    t = UI[ui]
    source, target = course['source_language'], course['target_language']
    counts = course_counts(course)
    seasons = []
    for season, label in course.get('seasons', {}).items():
        episodes = season_episodes(course, season)
        seasons.append({
            'key': season, 'label': label,
            'kind': t['kind_story'] if any(':chapter-' in ep['id'] for ep in episodes) else None,
            'print': season_name(season) if any(ep.get('transcript') for ep in episodes) else None,
            'episodes': [{
                'number': int(ep['episode']), 'title': ep['title'], 'page': transcript_name(ep),
                'summary': (f'{ep["phrases"]} {plural(ui, ep["phrases"], "phrases")}' if 'phrases' in ep
                            else first_paragraph(ep.get('description', ''))),
                'length': minutes(ui, int(ep.get('duration_ms') or 0)), 'transcript': ep.get('transcript'),
            } for ep in episodes],
        })
    stats = [
        (str(counts['episodes']), plural(ui, counts['episodes'], 'episodes')),
        (str(counts['practice']), plural(ui, counts['practice'], 'topics')),
        (str(counts['story']), plural(ui, counts['story'], 'chapters')),
        (hours(ui, counts['ms']), t['listening']),
    ]
    lead = first_paragraph(course.get('description', ''))
    return render(
        'course.html', assets=assets, title=course['title'], lang=ui, prefix='../', ui=ui, description=lead[:300],
        canonical=f'{base_url}/{course["slug"]}/', image=f'{base_url}/{course["slug"]}/{course["cover"]}',
        course=course, pair=f'{NAMES[ui][source]} → {NAMES[ui][target]}', heading=short_title(course['title']),
        lead=lead, stats=stats, links=course.get('links', {}), seasons=seasons,
        about=Markup(text_to_html(course.get('description', ''))),
    )


# ---------------------------------------------------------------------------
# Transcripts


def paragraphs(text: str) -> list[str]:
    return [p.strip() for p in text.split('\n\n') if p.strip()]


def sheet(course: dict, ep: dict, rows: list[tuple[str, str]], story: dict | None = None) -> dict:
    return {
        'cover': ep.get('cover') or course['cover'], 'label': course['seasons'].get(str(ep['season']), ''),
        'number': int(ep['episode']), 'title': ep['title'], 'rows': rows, 'story': story,
    }


def attach_transcripts(course: dict, practice: dict | None, stories: dict) -> dict[str, dict]:
    """Set episode['transcript'] for episodes we can render; return {episode id: sheet data}."""
    source, target = course['source_language'], course['target_language']
    sheets: dict[str, dict] = {}
    for ep in course['episodes']:
        practice_match = PRACTICE_ID.match(ep.get('id', ''))
        story_match = STORY_ID.match(ep.get('id', ''))
        if practice_match and practice:
            index = int(practice_match.group(1)) - 1
            if 0 <= index < len(practice['topics']):
                topic = practice['topics'][index]
                rows = [(practice_text(row, source), practice_text(row, target)) for row in topic['phrases']]
                if all(left and right for left, right in rows):
                    sheets[ep['id']] = sheet(course, ep, rows)
                    ep['phrases'] = len(rows)
        elif story_match:
            story_id, _, _, number = story_match.groups()
            story = stories.get(story_id)
            chapter = next((c for c in (story or {}).get('chapters', []) if int(c['chapter_number']) == int(number)), None)
            if chapter:
                rows = [(item['text'][source], item['text'][target]) for item in story_vocabulary_order(chapter)]
                text = {side: paragraphs(chapter['chapter_text'][lang]) for side, lang in (('source', source), ('target', target))}
                sheets[ep['id']] = sheet(course, ep, rows, text)
        if ep['id'] in sheets:
            ep['transcript'] = transcript_name(ep)
    return sheets


def doc_page(course: dict, title: str, sheets: list[dict], base_url: str, path: str, assets: dict,
             heading: str = 'h1', episode: dict | None = None) -> str:
    ui = course['ui']
    source, target = course['source_language'], course['target_language']
    listen = None
    if episode is not None:
        listen = {
            'cover': episode.get('cover') or course['cover'], 'label': course['seasons'].get(str(episode['season']), ''),
            'number': int(episode['episode']), 'title': episode['title'],
            'summary': '' if sheets else first_paragraph(episode.get('description', '')),
            'length': minutes(ui, int(episode.get('duration_ms') or 0)), 'links': course.get('links', {}),
        }
    return render(
        'transcript.html', assets=assets, title=f'{title} – {course["title"]}', lang=ui, prefix='../../', ui=ui,
        description=f'{UI[ui]["transcript"]}: {title}', canonical=f'{base_url}/{course["slug"]}/transcripts/{path}',
        image=None, sheets=sheets, heading=heading, course_title=course['title'], listen=listen,
        langs={'source': source, 'target': target}, names={'source': NAMES[ui][source], 'target': NAMES[ui][target]},
    )


def write_transcripts(directory: Path, course: dict, sheets: dict, base_url: str, assets: dict) -> list[str]:
    """Write one page per episode (with its transcript when available) and a printable page per season."""
    folder = directory / 'transcripts'
    if folder.exists():
        shutil.rmtree(folder)
    if not course['episodes']:
        return []
    folder.mkdir()
    written = []
    for season, label in course.get('seasons', {}).items():
        episodes = season_episodes(course, season)
        for ep in episodes:
            name = transcript_name(ep)
            sheet_list = [sheets[ep['id']]] if ep['id'] in sheets else []
            (folder / name).write_text(
                doc_page(course, ep['title'], sheet_list, base_url, name, assets, episode=ep), encoding='utf-8')
            written.append(name)
        with_sheets = [ep for ep in episodes if ep['id'] in sheets]
        if with_sheets:
            name = season_name(season)
            (folder / name).write_text(
                doc_page(course, label, [sheets[ep['id']] for ep in with_sheets], base_url, name, assets, 'h2'),
                encoding='utf-8')
            written.append(name)
    return written


# ---------------------------------------------------------------------------
# Site


def build_site(root: Path, courses: list[dict], base_url: str, practice: dict | None = None,
               stories: dict | None = None) -> None:
    """courses: catalog dicts with extra keys slug, cover and optionally story_cover (paths relative to course dir)."""
    base_url = base_url.rstrip('/')
    if practice is None:
        practice = load_practice()
    if stories is None:
        story_ids = {m.group(1) for c in courses for ep in c['episodes'] if (m := STORY_ID.match(ep.get('id', '')))}
        stories = {sid: data for sid in story_ids if (data := load_story(sid))}
    assets = write_assets(root)
    urls = [f'{base_url}/']
    for course in courses:
        course['ui'] = course_ui(course)
        directory = root / course['slug']
        sheets = attach_transcripts(course, practice, stories)
        for name in write_transcripts(directory, course, sheets, base_url, assets):
            urls.append(f'{base_url}/{course["slug"]}/transcripts/{name}')
        (directory / 'index.html').write_text(course_page(course, base_url, assets), encoding='utf-8')
        urls.append(f'{base_url}/{course["slug"]}/')
    (root / 'index.html').write_text(build_home(courses, base_url, assets), encoding='utf-8')
    sitemap = ''.join(f'<url><loc>{e(url)}</loc></url>' for url in sorted(urls))
    (root / 'sitemap.xml').write_text(
        f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{sitemap}</urlset>\n',
        encoding='utf-8')
    host = urlparse(base_url).path.rstrip('/')
    (root / 'robots.txt').write_text(
        f'User-agent: *\nDisallow: {host}/*/audio/\nAllow: /\n\nSitemap: {base_url}/sitemap.xml\n', encoding='utf-8')
