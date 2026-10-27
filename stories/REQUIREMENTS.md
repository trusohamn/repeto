Här är den justerade arkitekturen där **alla genererade transkript sparas som JSON** istället för `.txt`. Det gör parsningen helt automatisk, typstark och slipper specialtecken eller regextolkning.

---

### Mappstruktur

```text
polish_course/
└── stories/
    └── magical_radio/
        ├── cover.jpg                  <-- Omslagsbild (3000x3000px)
        │
        ├── complete/                  <-- Din manuella input
        │   └── pl.txt                 <-- Ren polsk råtext (kapitel 1–8)
        │
        └── generated/                 <-- Skapas helt av agenten
            ├── manifest.json          <-- Byggrecept, Spotify-metadata & kapitelmarkörer
            └── transcript.json        <-- Alla kapitel, siffer-ID:n och översättningar

```

---

### Filformat: `complete/pl.txt` (Din input)

Bara ren, läsbar polska uppdelad per kapitel:

```text
[Rozdział 1: Tajemnicze radio]
Jest sobota rano. Maja i Tomek rozglądają się po targu. W rogu stoi stary stół, a na stole – duże, drewniane radio z czerwonymi przyciskami. Tomek naciska pierwszy przycisk. Radio piszczy i zaczyna mówić: – Cześć, Maja! Cześć, Tomek! Z głośnika wylatuje mała, tajna mapa. – Patrz! – krzyczy Tomek. – Mapa pokazuje nasz ogród!

[Rozdział 2: Klucz w ogrodzie]
Dzieci biegną do ogrodu. Szukają starego dębu z mapy. Pod korzeniami leży małe, metalowe pudełko. W środku jest złoty klucz i dziwny, stary kompas. Kompas nie pokazuje północy – jego igła kręci się w kółko i wskazuje drewnianą szopę na narzędzia.

```

---

### Filformat: `generated/transcript.json` (Agentens output)

Varje ord och mening får ett unikt heltal som ID. ID:n är unika för hela berättelsen, även mellan kapitel och mellan `vocabulary` och `story_sentences`, och återanvänds aldrig. Språken ligger som ISO 639-1-nycklar under `text`.

```json
{
  "story_id": "magical_radio",
  "chapters": [
    {
      "chapter_number": 1,
      "titles": {
        "pl": "Tajemnicze radio",
        "sv": "Den hemliga radion",
        "en": "The Secret Radio"
      },
      "vocabulary": [
        {
          "id": 101,
          "text": {
            "pl": "rozglądają się",
            "sv": "ser sig omkring",
            "en": "look around"
          }
        },
        {
          "id": 102,
          "text": {
            "pl": "stary stół",
            "sv": "ett gammalt bord",
            "en": "an old table"
          }
        },
        {
          "id": 103,
          "text": {
            "pl": "drewniane radio",
            "sv": "en träradio",
            "en": "a wooden radio"
          }
        },
        {
          "id": 104,
          "text": {
            "pl": "czerwone przyciski",
            "sv": "röda knappar",
            "en": "red buttons"
          }
        },
        {
          "id": 105,
          "text": {
            "pl": "ono mówi",
            "sv": "den pratar",
            "en": "it speaks"
          }
        },
        {
          "id": 106,
          "text": {
            "pl": "tajna mapa",
            "sv": "en hemlig karta",
            "en": "a secret map"
          }
        }
      ],
      "story_sentences": [
        {
          "id": 107,
          "text": {
            "pl": "Jest sobota rano.",
            "sv": "Det är lördag förmiddag.",
            "en": "It is Saturday morning."
          }
        },
        {
          "id": 108,
          "text": {
            "pl": "Maja i Tomek rozglądają się po targu.",
            "sv": "Maja och Tomek ser sig omkring på loppisen.",
            "en": "Maja and Tomek look around the flea market."
          }
        },
        {
          "id": 109,
          "text": {
            "pl": "W rogu stoi stary stół, a na stole – duże, drewniane radio z czerwonymi przyciskami.",
            "sv": "I hörnet står ett gammalt bord, och på bordet står en stor träradio med röda knappar.",
            "en": "In the corner stands an old table, and on the table is a big wooden radio with red buttons."
          }
        },
        {
          "id": 110,
          "text": {
            "pl": "Tomek naciska pierwszy przycisk.",
            "sv": "Tomek trycker på den första knappen.",
            "en": "Tomek presses the first button."
          }
        },
        {
          "id": 111,
          "text": {
            "pl": "Radio piszczy i zaczyna mówić: – Cześć, Maja! Cześć, Tomek!",
            "sv": "Radion piper och börjar prata: – Hej, Maja! Hej, Tomek!",
            "en": "The radio beeps and speaks: 'Hello Maja! Hello Tomek!'"
          }
        },
        {
          "id": 112,
          "text": {
            "pl": "Z głośnika wylatuje mała, tajna mapa.",
            "sv": "Ur högtalaren flyger en liten, hemlig karta fram.",
            "en": "From the speaker flies out a small, secret map."
          }
        },
        {
          "id": 113,
          "text": {
            "pl": "– Patrz! – krzyczy Tomek. – Mapa pokazuje nasz ogród!",
            "sv": "– Titta! – ropar Tomek. – Kartan visar vår trädgård!",
            "en": "'Look!' shouts Tomek. 'The map shows our garden!'"
          }
        }
      ]
    }
  ]
}
```

---

### Ljudgenerering och konfiguration

Ljudet för varje kapitel ska spelas i denna ordning:

1. **Ord- och meningsövning:** spela först varje polskt original som ledtråd en gång. Spela därefter måltexten två gånger, med pauser så att barnet hinner tänka och härma uttalet. Övningen omfattar först kapitlets `vocabulary` i ordning och därefter `story_sentences` i ordning.
2. **Hela kapitlet:** spela därefter hela kapitlets sammanhängande berättelsetext en gång på målspråket, utan övningspauser eller upprepningar mellan meningarna.

Övningssekvensen följer den befintliga Repeto-modellen: ledtråd på källspråket, två sekunders tänkepaus, målfras, 2,5 sekunders repetitionspaus, samma målfras igen och därefter 2,5 sekunders paus. Pauser och varje delsegments tidsstämplar dokumenteras i manifestet. Den sammanhängande uppläsningen av kapitlet använder måltextens `story_sentences` i ordning.

Som standard genereras en version med svenska (`sv`) och en med engelska (`en`) som målspråk, båda med polska (`pl`) som käll-/ledtrådsspråk. Nya språk ska kunna läggas till utan ändringar i ljudmotorn. Källspråk, ett eller flera målspråk, röstval och röstinställningar, pauslängder, sökvägar, utdataformat och eventuella varaktighetsgränser ska kunna anges som kommandoradsargument (CLI-flaggor/”props”), inte vara hårdkodade. Standardvärden ska vara dokumenterade och kunna åsidosättas.

Transkriptet innehåller innehåll och översättningar. Manifestet innehåller genereringsinställningar, röstval, ljud- och kapiteltidsstämplar samt Spotify-/podcastmetadata. Validera hela kapitelutdata innan den publiceras; ett ofullständigt kapitel får inte presenteras som färdigt.

### Varför detta är bättre för din pipeline

- **Snabb åtkomst:** Ditt ljudskript hämtar alla meningar i ett kapitel via en vanlig array (`chapter.story_sentences.map(s => s.text[target_lang])`).
- **Ingen duplicering:** Vill du lägga till tyska (`de`) eller spanska (`es`) lägger agenten bara till nyckeln i samma objekt under befintligt ID.
- **Tydlig ansvarsfördelning:** `transcript.json` sköter text/språk med unika nummer, medan `manifest.json` sköter tidsstämplar, TTS-röstval och Spotify-beskrivningar.
