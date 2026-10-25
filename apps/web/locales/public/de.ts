import type { Catalog } from '../types';
import type { publicFr } from './fr';

export const publicDe: Catalog<typeof publicFr> = {
  skip: 'Zum Inhalt',
  install: 'Installieren',
  contact: 'Kontakt',
  devEnvironment: 'Entwicklungsumgebung',
  devAccess: 'Privater Zugang über WireGuard',
  preview: {
    label: 'Illustration eines Renderings',
    caption: 'Eine Szene als Eingabe, ein Bild als Ergebnis.',
    alt: 'Illustration einer spiegelnden Kugel und eines blauen Glaswürfels.',
  },
  password: { show: 'Passwort anzeigen', hide: 'Passwort verbergen' },
  walkthrough: {
    open: 'Ablauf in 3D erkunden',
    note: 'Illustration des Ablaufs. Dieses Schema zeigt keine Netzwerkaktivität in Echtzeit.',
  },
  home: {
    kicker: 'Verteiltes Rechnen, zugänglich',
    title: 'Ihre Berechnungen.',
    titleEm: 'In einer neuen Dimension.',
    description:
      'Rendern Sie eine 3D-Szene, durchsuchen Sie Dokumente oder verarbeiten Sie Daten in Stapeln. Silicium verteilt unterstützte Aufgaben auf seine Rechner und führt Ihre Ergebnisse an einem Ort zusammen.',
    start: 'Berechnung starten',
    explore: 'Anwendungen entdecken',
    contribute: 'Haben Sie einen Rechner frei?',
    contributeLink: 'Dem Netzwerk beitreten',
    note: 'Eine experimentelle Plattform. Konkrete Anwendungen.',
    usesKicker: 'Ihre Möglichkeiten',
    usesTitle: 'Vier Anwendungen. Ein Bereich.',
    usesText:
      'Wählen Sie eine Berechnungsart, bereiten Sie Ihre Daten vor und verfolgen Sie die Arbeit in Ihrem Bereich.',
    useAction: 'Diese Berechnung ausprobieren',
    uses: [
      {
        title: 'Machen Sie Szenen sichtbar.',
        tag: '3D-Rendering',
        text: 'Erstellen Sie eine Szene oder importieren Sie eine .cfg-Datei. Rechner berechnen die Bildkacheln, anschließend werden die Ergebnisse geprüft und zusammengesetzt.',
      },
      {
        title: 'Finden Sie die richtige Textstelle.',
        tag: 'Dokumentensuche',
        text: 'Stellen Sie Fragen zu PDFs, Word-Dokumenten oder Textdateien. Finden Sie passende Stellen mit Quelldokument und Seite.',
      },
      {
        title: 'Vom Text zur Tabelle.',
        tag: 'KI-Stapelverarbeitung',
        text: 'Ordnen Sie Bewertungen ein, fassen Sie Texte zusammen oder extrahieren Sie Felder. Eine Anweisung wird auf jeden Eintrag Ihrer Datei angewendet.',
      },
      {
        title: 'Vergleichen Sie Prüfsummen.',
        tag: 'SHA-256-Integrität',
        text: 'Berechnen Sie Prüfsummen für Dateiteile und erhalten Sie einen detaillierten Bericht zum Vergleich Ihrer Ergebnisse.',
      },
    ],
    processKicker: 'Von der Datei zum Ergebnis',
    processTitle: 'Vom Projekt zum Ergebnis.',
    processText:
      'Das Netzwerk übernimmt die Verteilung. Ihr Bereich hält Schritte, Fortschritt und Ergebnisse für Sie bereit.',
    steps: [
      {
        title: 'Projekt vorbereiten',
        text: 'Wählen Sie eine unterstützte Berechnung und importieren Sie Ihre Daten. Die erwarteten Formate werden vor dem Senden erklärt.',
      },
      {
        title: 'Das Netzwerk verteilt die Arbeit',
        text: 'Die Arbeit wird in unabhängige Teile zerlegt und von verfügbaren Rechnern übernommen.',
      },
      {
        title: 'Prüfungen verfolgen',
        text: 'Vor dem Zusammensetzen durchlaufen die Ergebnisse die für diese Berechnungsart vorgesehene Prüfung.',
      },
      {
        title: 'Ergebnisse abrufen',
        text: 'Betrachten Sie das Bild, durchsuchen Sie Dokumente oder laden Sie den Bericht aus Ihrem Projekt herunter.',
      },
    ],
    processAction: 'Den Ablauf verstehen',
    trustKicker: 'Nachvollziehbare Ausführung',
    trustTitle: 'Das Ergebnis zählt. Sein Weg ebenfalls.',
    trustText:
      'Verfolgen Sie die Berechnungsschritte und sehen Sie verfügbare Nachweise ein. Die Blockchain dokumentiert Vorgänge und speichert keine Dateiinhalte.',
    trustAction: 'Nachvollziehbarkeit entdecken',
    contributeKicker: 'Die andere Seite der Berechnung',
    contributeTitle: 'Ihr Rechner kann Teil des Netzwerks werden.',
    contributeText:
      'Installieren Sie Silicium Node, verbinden Sie Ihren Rechner und verfolgen Sie seine Teilnahme. Unter Linux übernehmen signierte APT- und DNF-Paketquellen Installation und Updates.',
    contributeAction: 'Silicium Node installieren',
    faqTitle: 'Bevor Sie beginnen',
    faq: [
      {
        question: 'Welche Projekte kann ich senden?',
        answer:
          'Die Formulare bieten vier Berechnungsarten: Bildberechnung, Dokumentensuche, KI-Textverarbeitung und SHA-256-Prüfsummen. Jede Art beschreibt ihre Formate und Grenzen.',
      },
      {
        question: 'Sind meine Dateien vertraulich?',
        answer:
          'Teilnehmende Rechner lesen die für die Berechnung benötigten Daten. Verwenden Sie Dateien, die Sie mit dem Netzwerk teilen können. Dateien werden nicht in die Blockchain geschrieben.',
      },
      {
        question: 'Wie installiere ich den Linux-Knoten?',
        answer:
          'Fügen Sie einmal die APT- oder DNF-Paketquelle hinzu und installieren Sie silicium-node mit Ihrem Paketmanager. Die Anleitung enthält Befehle und Voraussetzungen für den gewählten Kanal.',
      },
    ],
  },
  blueprint: {
    title: 'Ein Projekt, mehrere Rechenwege.',
    label: 'Ablaufdiagramm',
    input: 'Ihr Projekt',
    output: 'Ihr Ergebnis',
    compute: 'Rechner',
    verify: 'Prüfung',
    stages: ['Senden', 'Verteilen', 'Prüfen', 'Zusammensetzen'],
    descriptions: [
      'Ein Eingang für Ihre Datei und Einstellungen.',
      'Unabhängige Teile für verfügbare Rechner.',
      'Prüfungen passend zur angeforderten Berechnung.',
      'Ergebnisse werden in Ihrem Bereich zusammengeführt.',
    ],
  },
  live: {
    label: 'Netzwerkstatus',
    peers: 'Aktive Rechner',
    chain: 'Nachvollziehbarkeit',
    checked: 'Letzte Erfassung',
    pending: 'Warten auf den Dienst',
    unavailable: 'Daten nicht verfügbar',
    view: 'Detaillierten Status ansehen',
  },
  download: {
    kicker: 'Silicium Node',
    title: 'Einmal installieren.',
    titleEm: 'Am Netzwerk teilnehmen.',
    description:
      'Verbinden Sie Ihren Rechner mit Silicium. Wählen Sie System und Veröffentlichungskanal: Die Anleitung passt sich Ihrer Installation an.',
    system: 'Ihr System',
    linux: 'Linux',
    windows: 'Windows',
    channel: 'Veröffentlichungskanal',
    stable: 'Stabil',
    dev: 'Entwicklung',
    stableText: 'Öffentliche Produktionsquelle.',
    devText: 'Private Quelle, über WireGuard erreichbar.',
    version: 'Veröffentlichte Version',
    versionUnknown: 'Version nicht angegeben',
    arch: 'Architektur',
    native: 'Empfohlene Installation',
    nativeText:
      'APT oder DNF installiert das Paket und seine Abhängigkeiten. Neue Versionen erhalten Sie über den Paketmanager Ihres Systems.',
    windowsText:
      'Laden Sie das Installationsprogramm herunter, öffnen Sie es und folgen Sie den Schritten. Verbinden Sie anschließend Ihren Rechner in der Anwendung.',
    windowsAction: 'Für Windows herunterladen',
    portable: 'Lieber eine portable Version?',
    portableText:
      'Das AppImage steht zum manuellen Start auf einem System mit den erforderlichen Abhängigkeiten bereit.',
    portableAction: 'AppImage herunterladen',
    afterTitle: 'Wie geht es weiter?',
    steps: [
      {
        title: 'Anwendung öffnen',
        text: 'Starten Sie Silicium Node über die Anwendungen Ihres Systems.',
      },
      {
        title: 'Rechner verbinden',
        text: 'Geben Sie die angeforderten Informationen ein und prüfen Sie die Netzwerkverbindung.',
      },
      {
        title: 'Teilnahme verfolgen',
        text: 'Den Status Ihres Rechners finden Sie in Ihrem Silicium-Bereich.',
      },
    ],
    openSpace: 'Meinen Bereich öffnen',
    repoNote:
      'Die Pakete bleiben auf dem VPS. APT und DNF laden sie bei der Installation herunter und verwalten ihren lokalen Cache.',
    seo: 'Silicium Node installieren — APT- und DNF-Paketquellen',
  },
  repos: {
    manager: 'Ihre Distribution',
    apt: 'Debian / Ubuntu',
    dnf: 'Fedora / RHEL',
    signed: 'Signierte Pakete und Indizes',
    aptSigned: 'Signierte APT-Indizes',
    once: '01 — Paketquelle hinzufügen',
    onceHint: 'Einmal auf diesem Rechner ausführen.',
    install: '02 — Knoten installieren',
    update: 'Für künftige Updates',
    copy: 'Kopieren',
    copied: 'Kopiert',
    copyFailed: 'Zwischenablage nicht verfügbar. Wählen Sie die Befehle unten aus.',
    devTitle: 'Entwicklungszugang vorbereiten',
    devText:
      'Aktivieren Sie WireGuard und installieren Sie das mit Ihrem Zugang bereitgestellte CA-Zertifikat. Erledigen Sie dies vor dem Hinzufügen der Paketquelle.',
    caTitle: 'Zertifikat auf diesem System installieren',
    caText:
      'Legen Sie die bereitgestellte Datei als silicium-dev-ca.crt.pem im aktuellen Ordner ab und führen Sie diese Befehle aus. Ist es bereits installiert, fahren Sie mit Schritt 01 fort.',
    caCode: 'Entwicklungszertifikat — einmal',
    chooseOne:
      'Wählen Sie pro Rechner einen Kanal: Stabil und Entwicklung verwenden denselben Paketnamen.',
    trouble: 'Der Paketmanager findet das Paket nicht?',
    troubleText:
      'Prüfen Sie, ob die Paketquelle hinzugefügt wurde. Prüfen Sie bei Entwicklung auch WireGuard und das CA-Zertifikat.',
    diagnostic: 'Paketquelle prüfen',
  },
  footer: {
    title: 'Rechenleistung teilen.',
    description:
      'Starten Sie Berechnungen, verfolgen Sie deren Ausführung oder stellen Sie dem Netzwerk einen Rechner bereit.',
    product: 'Entdecken',
    participate: 'Teilnehmen',
    resources: 'Verstehen',
    uses: 'Anwendungen',
    network: 'Netzwerkstatus',
    source: 'Experimentelles Projekt für verteiltes Rechnen',
  },
};
