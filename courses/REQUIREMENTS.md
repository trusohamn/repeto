Story- och övningsmaterial organiseras under `courses/`. Delade
vokabulärövningar har en enda källa; berättelser ligger under sin
språkriktnings kursmapp.

---

### Mappstruktur

```text
polish_course/
├── courses/
│   ├── practice/
│   │   └── transcript.json            <-- Delad vokabulärkälla för språkpraktik
│   ├── REQUIREMENTS.md
│   └── swedish-polish/
│       └── stories/
│           └── magical_radio/
│               ├── cover_se_pl.jpeg
│               ├── complete/
│               │   └── pl.txt         <-- Oförändrad polsk originaltext
│               └── generated/
│                   ├── transcript.json
│                   ├── manifest.json
│                   └── audio/sv_pl/   <-- Renderade filer och tidsstämplar
└── code/
    ├── transcription.py               <-- Renderer för delad vokabulärpraktik
    └── story_course.py                <-- Storyrenderer och podcastpaketerare
```

---

### Filformat: `courses/swedish-polish/stories/magical_radio/complete/pl.txt` (Din input)

Bara ren, läsbar polska uppdelad per kapitel:

```text
[Rozdział 1: Tajemnicze radio]
Jest sobota rano. Maja i Tomek rozglądają się po targu. W rogu stoi stary stół, a na stole – duże, drewniane radio z czerwonymi przyciskami. Tomek naciska pierwszy przycisk. Radio piszczy i zaczyna mówić: – Cześć, Maja! Cześć, Tomek! Z głośnika wylatuje mała, tajna mapa. – Patrz! – krzyczy Tomek. – Mapa pokazuje nasz ogród!

[Rozdział 2: Klucz w ogrodzie]
Dzieci biegną do ogrodu. Szukają starego dębu z mapy. Pod korzeniami leży małe, metalowe pudełko. W środku jest złoty klucz i dziwny, stary kompas. Kompas nie pokazuje północy – jego igła kręci się w kółko i wskazuje drewnianą szopę na narzędzia.

```

---

### Filformat: `generated/transcript.json` (Kursens output)

Varje vokabulärord eller -uttryck får ett positivt heltal som ID. ID:n är unika för hela berättelsen, även mellan kapitel, och återanvänds aldrig. Berättelsen lagras som en enda sammanhängande `chapter_text` per tillgängligt uppläsningsspråk; meningar i berättelsen får inga separata översättningar eller övnings-ID:n. Språken i `text` är ISO 639-1-koder.

```json
{
  "story_id": "magical_radio",
  "titles": {
    "pl": "Magiczne Radio",
    "sv": "Den magiska radion",
    "en": "The Magical Radio"
  },
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
      "chapter_text": {
        "pl": "Jest sobota rano. Maja i Tomek rozglądają się po targu. W rogu stoi stary stół, a na stole – duże, drewniane radio z czerwonymi przyciskami. Tomek naciska pierwszy przycisk. Radio piszczy i zaczyna mówić: – Cześć, Maja! Cześć, Tomek! Z głośnika wylatuje mała, tajna mapa. – Patrz! – krzyczy Tomek. – Mapa pokazuje nasz ogród!"
      }
    }
  ]
}
```

---

### Vokabulärens täckning

Varje kapitel ska ha tillräckligt med ord och korta uttryck för att ett barn med
begränsade förkunskaper ska kunna följa kapitlets personer, plats, handling och
viktiga händelser när hela texten läses. Gå igenom hela kapitlet och ta med
berättelsekritiska substantiv, verb/handlingar, beskrivningar och uttryck samt
småord eller sambandsord när de behövs för att förstå betydelsen. Vokabulären
ska förbereda barnet för just det kapitlet; anta inte att ett viktigt ord redan
har lärts i ett senare kapitel. Använd naturliga ord eller korta fraser, inte
hela meningar som ersätter översättning eller övning av berättelsen. Det finns
inget fast antal: välj täckning efter kapitlets innehåll och svårighetsgrad.

### Ljudgenerering och konfiguration

Ljudet för varje kapitel ska spelas i denna ordning:

1. **Boktitel:** i kapitel 1 sägs bokens titel en gång i början, före
   ordövningen. Titeln ska inte läsas upp igen i kapiteltexten.
2. **Ordövning:** öva bara ord och uttryck i kapitlets `vocabulary`, i en
   deterministiskt slumpad ordning som skiljer sig från berättelsens kronologi.
   Ordningen blandas separat per kapitel och är densamma vid omrendering, så
   ljudet blir reproducerbart. Spela varje uttryck på barnets modersmål en gång
   som ledtråd, därefter uttrycket på målspråket två gånger, med pauser.
3. **Hela kapitlet:** spela därefter hela kapitlets sammanhängande original-/måltext en gång på målspråket. Översätt inte och öva inte berättelsens enskilda meningar var för sig.

Övningssekvensen följer den befintliga Repeto-modellen: svensk ledtråd, två sekunders tänkepaus, polsk målfras, 2,5 sekunders repetitionspaus, samma polska fras igen och därefter 2,5 sekunders paus. Övningsfraserna blandas deterministiskt per kapitel, utan att ändra berättelsetexten eller transkriptets permanenta ID:n. Pauser och varje delsegments tidsstämplar dokumenteras i manifestet. Kapiteluppläsningen använder hela `chapter_text`-strängen på målspråket som en enda sammanhängande text. Kapitel 1:s boksintroduktion och dess tidsstämpel dokumenteras separat i manifestet.

Som standard används svenska (`sv`) som ledtråds-/modersmål och polska (`pl`) som målspråk. Den polska originaltexten läses sedan upp en gång som hela kapitlet. Nya språk ska kunna läggas till utan ändringar i ljudmotorn: vokabulär har parallella texter för övningsspråken, medan varje kapitel har en hel `chapter_text` per tillgängligt uppläsningsspråk. Berättelsens meningar behöver inte segmenteras eller översättas individuellt. Källspråk, ett eller flera målspråk, röstval och röstinställningar, pauslängder, sökvägar, utdataformat och eventuella varaktighetsgränser ska kunna anges som kommandoradsargument (CLI-flaggor/”props”), inte vara hårdkodade. Standardvärden ska vara dokumenterade och kunna åsidosättas.

Transkriptet innehåller innehåll och översättningar. Manifestet innehåller genereringsinställningar, röstval, ljud- och kapiteltidsstämplar samt Spotify-/podcastmetadata. Validera hela kapitelutdata innan den publiceras; ett ofullständigt kapitel får inte presenteras som färdigt.

### Körning

Storyverktyget finns i `code/story_course.py`. Validera transkriptet och
jämför det polska originalet mot samtliga kapitelmeningar:

```sh
.venv/bin/python code/story_course.py --list
```

Generera som standard polsk vokabulärövning med långsamma svenska ledtrådar och därefter uppläsning av hela kapitlet på polska:

```sh
.venv/bin/python code/story_course.py --source-language sv --target pl
```

Använd `--help` för alla alternativ. Källspråk, mål, röster (`--voice LANG=VOICE`), hastigheter (`--rate LANG=RATE`), tonhöjd (`--pitch LANG=PITCH`), pauser, ljudformat, varaktighetsgräns, transkript, cache och utdatasökvägar är konfigurerbara. En varaktighetsgräns avvisar ett helt kapitel som överskrider gränsen; den skapar aldrig ett ofullständigt slutspår.

Standardhastigheten för polska och svenska är `-15%`; svenska är avsiktligt långsammare för tydligare uttal.

Podcastflöden skapas bara med `--package-podcast`. När en berättelse läggs till
i en befintlig språkshow används showens befintliga omslag och ägaruppgifter;
kapitlen läggs till som en ny säsong under `audio/stories/<story-id>/`. En ny,
separat show kräver omslagsbild och kontaktadress för RSS. Ljudfiler och flöden
publiceras inte automatiskt till Spotify. Publicering sker först efter separat
commit/push och en lyckad GitHub Pages-deploy.

### Varför detta är bättre för din pipeline

- **Sammanhängande berättelse:** Ljudskriptet läser ett helt kapitel från `chapter.chapter_text[target_lang]`; berättelsen segmenteras inte till meningar för översättningsövning.
- **Nya språk:** Lägg till översättningar i vokabulär och en hel `chapter_text` för varje nytt uppläsningsspråk som ska stödjas.
- **Tydlig ansvarsfördelning:** `transcript.json` sköter vokabulär och hela kapiteltexter, medan `manifest.json` sköter tidsstämplar, TTS-röstval och Spotify-beskrivningar.
