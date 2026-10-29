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
│   └── stories/                       <-- Berättelser delade av alla språkriktningar
│       └── magical_radio/
│           ├── cover.jpeg             <-- Gemensamt berättelseomslag
│           ├── complete/
│           │   └── pl.txt             <-- Oförändrad polsk originaltext
│           └── generated/
│               ├── transcript.json    <-- `chapter_text` på polska, engelska och ryska
│               ├── manifest.json      <-- Gemensamt för alla riktningar
│               ├── audio/sv_pl/       <-- Tidsstämplar, svenska till polska
│               ├── audio/sv_en/       <-- Tidsstämplar, svenska till engelska
│               └── audio/sv_ru/       <-- Tidsstämplar, svenska till ryska
└── code/
    ├── transcription.py               <-- Renderer för delad vokabulärpraktik
    └── story_course.py                <-- Storyrenderer och podcastpaketerare
```

---

### Filformat: `courses/stories/magical_radio/complete/pl.txt` (Din input)

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

**Namn på figurer:**

- **Inom en kurs bevaras namnen.** I en och samma språkversion (en kurs, till exempel svenska–engelska) heter figurerna likadant i alla kapitel, rubriker, ordövningar och avsnitt. Ett namn får aldrig bytas mitt i en kurs.
- **Vid byte av målspråk anpassas namnen.** När en berättelse översätts till ett nytt målspråk får figurerna välbekanta namn på det språket, så att berättelsen känns naturlig för lyssnarna. Exempel för *Magiczne Radio* på engelska: Maja → Maya, Tomek → Tom, Radiofon → Radiophone. På ryska: Maja → Маша, Tomek → Миша, Radiofon → Радиофон.
- **Varje berättelse har egna namn.** Namnvalen gäller bara den berättelsen; en annan berättelse väljer sina egna namn.
- Det polska originalet ändras aldrig. Påhittade magiska ord, som trollordet `Reparo`, uttalas likadant på alla språk. På språk med annat alfabet skrivs de med det alfabetet så att talsyntesen uttalar dem rätt, till exempel `Репаро` på ryska.

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

Varje kapitel ska ha tillräckligt med ord och korta uttryck för att en nybörjare med
begränsade förkunskaper ska kunna följa kapitlets personer, plats, handling och
viktiga händelser när hela texten läses. Gå igenom hela kapitlet och ta med
berättelsekritiska substantiv, verb/handlingar, beskrivningar och uttryck samt
småord eller sambandsord när de behövs för att förstå betydelsen. Vokabulären
ska förbereda lyssnaren för just det kapitlet; anta inte att ett viktigt ord redan
har lärts i ett senare kapitel. Använd naturliga ord eller korta fraser, inte
hela meningar som ersätter översättning eller övning av berättelsen. Det finns
inget fast antal: välj täckning efter kapitlets innehåll och svårighetsgrad.

### Ljudgenerering och konfiguration

Hela kapitel och boktiteln använder som standard Azure Speech, Harper
MAI-Voice-2.1 med stilen `audiobook` och hastigheten `-12%` för svenska,
polska och engelska. Ryska använder Azure `ru-RU-SvetlanaNeural` utan stil,
eftersom rysk Harper gav hörbara störljud i bakgrunden. Uppläsningsspråket styr röstvalet,
oberoende av barnets modersmål. Ordövningar och övningsavsnitt använder samma Neural-röster
via licensierad Azure Speech (`--tts-engine azure`, standard), eftersom Azures
villkor tillåter publicering av ljudet. `--tts-engine edge` (den inofficiella
Edge-uppläsningen) får bara väljas uttryckligen. Manifestet anger `tts_engine`.
Azure-inställningar anges separat med `--narration-voice`,
`--narration-rate` och `--narration-style`. Fel får inte ge tyst återgång till
Edge; äldre beteende väljs uttryckligen med `--narration-engine edge`.

Godkända kapitelanvisningar registreras i `generated/narration.json` som
språkkod -> kapitelnummer -> passagearray eller relativ JSON-fil. Texten
ska rekonstruera originalkapitlet exakt. Saknade anvisningar ger vanlig
sammanhängande audiobook-uppläsning, inte påstått handregisserat ljud.
Manifestet ska innehålla uppläsningsmotor, röst, stil, språk och exakt SSML.

Ljudet för varje kapitel ska spelas i denna ordning:

Varje inspelning inleds med kapitlets nummer och titel på målspråket
(t.ex. "Rozdział drugi. Głos z radia."), med samma röst
som berättelsen och repetitionspausen före första uppläsningen. I kapitel 1
kommer boktiteln först. Kapitelrubriken sägs bara en gång och registreras
med text och tidsstämplar i `chapter_introduction` i båda manifesten.

1. **Boktitel:** i kapitel 1 sägs bokens titel en gång i början, före
   första uppläsningen. Titeln ska inte läsas upp igen i kapiteltexten.
2. **Första lyssningen:** spela hela kapitlet sammanhängande på målspråket,
   så att lyssnaren hör orden i sitt sammanhang före övningen.
3. **Ordövning:** öva bara ord och uttryck i kapitlets `vocabulary`, i en
   deterministiskt slumpad ordning som skiljer sig från berättelsens kronologi.
   Ordningen blandas separat per kapitel och är densamma vid omrendering, så
   ljudet blir reproducerbart. Spela varje uttryck på barnets modersmål en gång
   som ledtråd, därefter uttrycket på målspråket två gånger, med pauser.
4. **Andra lyssningen:** spela samma kapitelinspelning igen efter övningen.
   Återanvänd exakt samma ljudklipp utan ett nytt TTS-anrop. Översätt inte
   och öva inte berättelsens enskilda meningar var för sig.

Använd den konfigurerade repetitionspausen mellan delarna (standard 2,5 sekunder).
Markera båda övergångarna mellan berättelse och övning med en mjuk tvåtonssignal
(620 ms), med repetitionspausen före och efter. Signalen skapas lokalt och
dess riktning och tidsstämplar sparas i `transitions`.
Manifestets `sequence` är `["story", "practice", "story"]`.
`chapter_readings` innehåller båda uppläsningarnas text och tidsstämplar i
kronologisk ordning. Behåll `chapter_reading` för den sista uppläsningen
så att befintliga verktyg fortsätter fungera.

Övningssekvensen följer den befintliga Repeto-modellen: svensk ledtråd, två sekunders tänkepaus, polsk målfras, 2,5 sekunders repetitionspaus, samma polska fras igen och därefter 2,5 sekunders paus. Övningsfraserna blandas deterministiskt per kapitel, utan att ändra berättelsetexten eller transkriptets permanenta ID:n. Pauser och varje delsegments tidsstämplar dokumenteras i manifestet. Kapiteluppläsningen använder hela `chapter_text`-strängen på målspråket som en enda sammanhängande text. Kapitel 1:s boksintroduktion och dess tidsstämpel dokumenteras separat i manifestet.

Som standard används svenska (`sv`) som ledtråds-/modersmål och polska (`pl`) som målspråk. Hela den polska originaltexten spelas före ordövningen och en gång till efteråt. Nya språk ska kunna läggas till utan ändringar i ljudmotorn: vokabulär har parallella texter för övningsspråken, medan varje kapitel har en hel `chapter_text` per tillgängligt uppläsningsspråk. Berättelsens meningar behöver inte segmenteras eller översättas individuellt. Källspråk, ett eller flera målspråk, röstval och röstinställningar, pauslängder, sökvägar, utdataformat och eventuella varaktighetsgränser ska kunna anges som kommandoradsargument (CLI-flaggor/”props”), inte vara hårdkodade. Standardvärden ska vara dokumenterade och kunna åsidosättas.

Transkriptet innehåller innehåll och översättningar. Manifestet innehåller genereringsinställningar, röstval, ljud- och kapiteltidsstämplar samt Spotify-/podcastmetadata. Validera hela kapitelutdata innan den publiceras; ett ofullständigt kapitel får inte presenteras som färdigt.

### Körning

Storyverktyget finns i `code/story_course.py`. Validera transkriptet och
jämför det polska originalet mot samtliga kapitelmeningar:

```sh
.venv/bin/python code/story_course.py --list
```

Generera som standard hela kapitlet på polska, ordövning med långsamma svenska ledtrådar och samma kapitel en gång till:

```sh
.venv/bin/python code/story_course.py --source-language sv --target pl
```

Använd `--help` för alla alternativ. Källspråk, mål, röster (`--voice LANG=VOICE`), hastigheter (`--rate LANG=RATE`), tonhöjd (`--pitch LANG=PITCH`), pauser, ljudformat, varaktighetsgräns, transkript, cache och utdatasökvägar är konfigurerbara. En varaktighetsgräns avvisar ett helt kapitel som överskrider gränsen; den skapar aldrig ett ofullständigt slutspår.

Standardhastigheten för polska och svenska i ordövningar är `-15%`;
svenska är avsiktligt långsammare för tydligare uttal. Azure-uppläsning
använder separat hastighet och eventuella kapitelanvisningar.

Podcastflöden skapas bara med `--package-podcast`. När en berättelse läggs till
i en befintlig språkshow används showens befintliga omslag och ägaruppgifter;
kapitlen läggs till som en ny säsong under `audio/stories/<story-id>/`.
Paketeringen flyttar MP3-filen dit i stället för att kopiera den, så varje
avsnitt finns bara en gång. Tidsstämpel-JSON stannar i `generated/audio/`, och
byggmanifestet anger `packaged_audio`. En ny,
separat show kräver omslagsbild och kontaktadress för RSS. Ljudfiler och flöden
publiceras inte automatiskt till Spotify. Publicering sker först efter separat
commit/push och en lyckad GitHub Pages-deploy.

Berättelsens omslag ska kopieras till `images/stories/<story-id>/cover.jpeg`
i podcastmappen och länkas från varje kapitel med `itunes:image`. Showens
befintliga omslag ska vara oförändrat. Välj berättelseomslag med `--cover`;
annars används riktningsfilen, till exempel `cover_se_pl.jpeg`, sedan det
gemensamma `cover.jpeg` och sist äldre `cover.jpg`. Saknat omslag ska avbryta
paketeringen med ett tydligt fel.

Publicerade omslag får ett innehållsbaserat filnamn, till exempel
`cover-1719c6cd.jpeg`, eftersom Spotify och andra appar cachar bilder per URL.
Ett nytt omslag läggs in som `cover.jpeg` (eller skriver över nuvarande
`cover-<hash>.jpeg`); flödesbyggaren byter namn, tar bort den gamla versionen
och uppdaterar flöde och webbsida. Bara en version av varje bild får finnas.

Renderingar hamnar som standard i `generated/audio/<källspråk>_<målspråk>/`.
Byggmanifestet delas av alla riktningar: att rendera ett målspråk får inte ta
bort andra målspråks kapitelposter, och `renders` sparar inställningarna per
riktning. Svenska–engelska avsnitt läggs som en egen säsong i
`swedish-english` med svensk beskrivning: ”Lyssna på ett kapitel ur
berättelsen The Magical Radio på engelska, öva orden med svenska ledtrådar och
lyssna sedan på kapitlet igen.”

### Varför detta är bättre för din pipeline

- **Sammanhängande berättelse:** Ljudskriptet läser ett helt kapitel från `chapter.chapter_text[target_lang]`; berättelsen segmenteras inte till meningar för översättningsövning.
- **Nya språk:** Lägg till översättningar i vokabulär och en hel `chapter_text` för varje nytt uppläsningsspråk som ska stödjas.
- **Tydlig ansvarsfördelning:** `transcript.json` sköter vokabulär och hela kapiteltexter, medan `manifest.json` sköter tidsstämplar, TTS-röstval och Spotify-beskrivningar.
