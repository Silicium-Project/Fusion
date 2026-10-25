import type { Catalog } from '../types';
import type { publicFr } from './fr';

export const publicEn: Catalog<typeof publicFr> = {
  skip: 'Skip to content',
  install: 'Install',
  contact: 'Contact',
  devEnvironment: 'Development environment',
  devAccess: 'Private access through WireGuard',
  preview: {
    label: 'Render illustration',
    caption: 'A scene goes in. An image comes out.',
    alt: 'Illustration of a reflective sphere and a blue glass cube.',
  },
  password: { show: 'Show password', hide: 'Hide password' },
  walkthrough: {
    open: 'Explore the process in 3D',
    note: 'An illustration of the process. This diagram does not show live network activity.',
  },
  home: {
    kicker: 'Distributed computing, within reach',
    title: 'Your computation.',
    titleEm: 'A different scale.',
    description:
      'Render a 3D scene, explore your documents or process data in batches. Silicium distributes supported tasks across its machines and brings your results into one workspace.',
    start: 'Start a computation',
    explore: 'Explore the use cases',
    contribute: 'Have a machine available?',
    contributeLink: 'Join the network',
    note: 'An experimental platform. Concrete use cases.',
    usesKicker: 'What you can do',
    usesTitle: 'Four uses. One workspace.',
    usesText:
      'Choose a computation type, prepare your data and follow the work from your workspace.',
    useAction: 'Try this computation',
    uses: [
      {
        title: 'Bring your scenes to life.',
        tag: '3D rendering',
        text: 'Build a scene or import a .cfg file. Machines compute the image tiles, then the results are checked and assembled.',
      },
      {
        title: 'Find the right passage.',
        tag: 'Document search',
        text: 'Ask questions about your PDFs, Word documents or text files. Find relevant passages with their source document and page.',
      },
      {
        title: 'Turn text into a table.',
        tag: 'AI batch processing',
        text: 'Classify reviews, summarise text or extract fields. One instruction is applied to every item in your file.',
      },
      {
        title: 'Compare the fingerprints.',
        tag: 'SHA-256 integrity',
        text: 'Compute fingerprints for the parts of a file and retrieve a detailed report to compare your results.',
      },
    ],
    processKicker: 'From file to result',
    processTitle: 'From project to result.',
    processText:
      'The network handles distribution. Your workspace keeps the stages, progress and results within reach.',
    steps: [
      {
        title: 'Prepare your project',
        text: 'Choose a supported computation and import your data. The required formats are explained before submission.',
      },
      {
        title: 'Let the network distribute',
        text: 'The work is split into independent parts, handled by available machines.',
      },
      {
        title: 'Follow the checks',
        text: 'Results go through the verification defined for that computation type before assembly.',
      },
      {
        title: 'Retrieve your results',
        text: 'View the render, search your documents or download the report from your project.',
      },
    ],
    processAction: 'Understand the process',
    trustKicker: 'An execution you can follow',
    trustTitle: 'The result matters. So does its journey.',
    trustText:
      'Follow computation stages and inspect the available records. The blockchain tracks operations, rather than storing the contents of your files.',
    trustAction: 'Explore traceability',
    contributeKicker: 'The other side of computing',
    contributeTitle: 'Your machine can be part of the network.',
    contributeText:
      'Install Silicium Node, connect your machine and follow its participation. On Linux, signed APT and DNF repositories handle installation and updates.',
    contributeAction: 'Install Silicium Node',
    faqTitle: 'Before you start',
    faq: [
      {
        question: 'What projects can I submit?',
        answer:
          'The forms offer four computation types: image rendering, document search, AI text processing and SHA-256 fingerprints. Each type describes its formats and limits.',
      },
      {
        question: 'Are my files confidential?',
        answer:
          'Participating machines read the data needed for computation. Use files you can share with the network. Files are not written to the blockchain.',
      },
      {
        question: 'How do I install the Linux node?',
        answer:
          'Add the APT or DNF repository once, then install silicium-node through your package manager. The guide provides commands and requirements for your selected channel.',
      },
    ],
  },
  blueprint: {
    title: 'One project, several computation paths.',
    label: 'Process diagram',
    input: 'Your project',
    output: 'Your result',
    compute: 'Compute machines',
    verify: 'Verification',
    stages: ['Submit', 'Distribute', 'Verify', 'Assemble'],
    descriptions: [
      'One entry point for your file and settings.',
      'Independent parts assigned to available machines.',
      'Checks suited to the requested computation type.',
      'Results brought together in your workspace.',
    ],
  },
  live: {
    label: 'Network status',
    peers: 'Active machines',
    chain: 'Traceability',
    checked: 'Last reading',
    pending: 'Waiting for the service',
    unavailable: 'Data unavailable',
    view: 'View detailed status',
  },
  download: {
    kicker: 'Silicium Node',
    title: 'Install once.',
    titleEm: 'Join the network.',
    description:
      'Connect your machine to Silicium. Choose your system and release channel: the instructions adapt to your installation.',
    system: 'Your system',
    linux: 'Linux',
    windows: 'Windows',
    channel: 'Release channel',
    stable: 'Stable',
    dev: 'Development',
    stableText: 'Public production repository.',
    devText: 'Private repository, accessible with WireGuard.',
    version: 'Published version',
    versionUnknown: 'Version not provided',
    arch: 'Architecture',
    native: 'Recommended installation',
    nativeText:
      'APT or DNF installs the package and its dependencies. Future releases are available through your system package manager.',
    windowsText:
      'Download the installer, open it and follow the steps. You can then connect your machine from the application.',
    windowsAction: 'Download for Windows',
    portable: 'Prefer a portable version?',
    portableText:
      'The AppImage is available for manual launching on a system with its required dependencies.',
    portableAction: 'Download the AppImage',
    afterTitle: 'What comes next?',
    steps: [
      {
        title: 'Open the application',
        text: 'Launch Silicium Node from your system applications.',
      },
      {
        title: 'Connect your machine',
        text: 'Enter the requested information and check the network connection.',
      },
      {
        title: 'Follow its participation',
        text: 'Find the status of your machine in your Silicium workspace.',
      },
    ],
    openSpace: 'Open my workspace',
    repoNote:
      'Packages remain hosted on the VPS. APT and DNF download them during installation and manage their local cache.',
    seo: 'Install Silicium Node — APT and DNF repositories',
  },
  repos: {
    manager: 'Your distribution',
    apt: 'Debian / Ubuntu',
    dnf: 'Fedora / RHEL',
    signed: 'Signed packages and indexes',
    aptSigned: 'Signed APT indexes',
    once: '01 — Add the repository',
    onceHint: 'Run once on this machine.',
    install: '02 — Install the node',
    update: 'For future updates',
    copy: 'Copy',
    copied: 'Copied',
    copyFailed: 'Clipboard unavailable. Select the commands below.',
    devTitle: 'Prepare development access',
    devText:
      'Enable WireGuard and install the development CA certificate supplied with your access. Complete these steps before adding the repository.',
    caTitle: 'Install the certificate on this system',
    caText:
      'Place the supplied file in your current directory as silicium-dev-ca.crt.pem, then run these commands. If it is already installed, continue to step 01.',
    caCode: 'Development certificate — once',
    chooseOne: 'Choose one channel per machine: stable and development use the same package name.',
    trouble: 'The package manager cannot find the package?',
    troubleText:
      'Check that the repository has been added. For development, also check WireGuard and the CA installation.',
    diagnostic: 'Check the repository',
  },
  footer: {
    title: 'Computing is better shared.',
    description: 'Run computations, follow their execution or contribute a machine to the network.',
    product: 'Discover',
    participate: 'Participate',
    resources: 'Understand',
    uses: 'Use cases',
    network: 'Network status',
    source: 'An experimental distributed computing project',
  },
};
