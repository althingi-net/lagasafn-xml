import { useParams, A } from '@solidjs/router';
import { createSignal, onMount } from 'solid-js';
import Header from '~/components/Header';

interface TableOfContentsItem {
    id: string;
    title: string;
    level: number;
}

interface Law {
    nr: string;
    name: string;
    chapter?: number;
    article?: number;
    status: 'OK' | string;
    content?: string;
    toc: TableOfContentsItem[];
    date?: string;
}

// Mock data for individual law view
const MOCK_LAW: Law = {
    nr: '6/2025',
    name: 'Forsetaúrskurður um skiptingu starfa ráðherra',
    chapter: 12,
    status: 'OK',
    date: '14. mars',
    toc: [
        { id: '1', title: 'Forsetisráðherra', level: 1 },
        { id: '2', title: 'Atvinnuvegaráðherra', level: 1 },
        { id: '3', title: 'Dómsmálaráðherra', level: 1 },
        { id: '4', title: 'Félags- og húsnæðismálaráðherra', level: 1 },
        { id: '5', title: 'Fjármála- og efnahagsráðherra', level: 1 },
        { id: '6', title: 'Heilbrigðisráðherra', level: 1 },
        { id: '7', title: 'Innviðaráðherra', level: 1 },
        { id: '8', title: 'Menningar-, nýsköpunar- og háskólaráðherra', level: 1 },
        { id: '9', title: 'Mennta- og barnamálaráðherra', level: 1 },
        { id: '10', title: 'Umhverfis-, orku- og loftslagsráðherra', level: 1 },
        { id: '11', title: 'Utanríkisráðherra', level: 1 },
        { id: '12', title: '', level: 1 },
    ],
    content: `Tók gildi 15. mars 2025. Breytt með: Forsetaúrskurður nr. 9/2025 (tók gildi 24. mars 2025).

Samkvæmt tillögu forsætisráðherra og með skírskotun til 15. gr. stjórnarskrárinnar, laga um Stjórnarráð Íslands og forsetaúrskurðar um skiptingu Stjórnarráðs Íslands í ráðuneyti er störfum þannig skipt með ráðherrum:

■ 1. gr. Forsetisráðherra.
□ Kristín Frostadóttir fer með stjórnarmálefni sem heyra undir forsætisráðuneytið skv. 1. gr. forsetaúrskurðar um skiptingu stjórnarmálefna milli ráðuneyta í Stjórnarráði Íslands og ber embættisheitið forsætisráðherra.

■ 2. gr. Atvinnuvegaráðherra.
□ Hanna Katrín Friðriksson fer með stjórnarmálefni sem heyra undir atvinnuvegaráðuneytið skv. 2. gr. forsetaúrskurðar um skiptingu stjórnarmálefna milli ráðuneyta í Stjórnarráði Íslands og ber embættisheitið atvinnuvegaráðherra.

■ 3. gr. Dómsmálaráðherra.
□ Þorbjörg Sigríður Gunnlaugsdóttir fer með stjórnarmálefni sem heyra undir dómsmálaráðuneytið skv. 3. gr. forsetaúrskurðar um skiptingu stjórnarmálefna milli ráðuneyta í Stjórnarráði Íslands og ber embættisheitið dómsmálaráðherra.

■ 4. gr. Félags- og húsnæðismálaráðherra.
□ Þorsteinn Jónsson fer með stjórnarmálefni sem heyra undir félags- og húsnæðismálaráðuneytið skv. 4. gr. forsetaúrskurðar um skiptingu stjórnarmálefna milli ráðuneyta í Stjórnarráði Íslands og ber embættisheitið félags- og húsnæðismálaráðherra.

■ 5. gr. Fjármála- og efnahagsráðherra.
□ Þorsteinn Jónsson fer með stjórnarmálefni sem heyra undir fjármála- og efnahagsráðuneytið skv. 5. gr. forsetaúrskurðar um skiptingu stjórnarmálefna milli ráðuneyta í Stjórnarráði Íslands og ber embættisheitið fjármála- og efnahagsráðherra.

■ 6. gr. Heilbrigðisráðherra.
□ Þorsteinn Jónsson fer með stjórnarmálefni sem heyra undir heilbrigðisráðuneytið skv. 6. gr. forsetaúrskurðar um skiptingu stjórnarmálefna milli ráðuneyta í Stjórnarráði Íslands og ber embættisheitið heilbrigðisráðherra.

■ 7. gr. Innviðaráðherra.
□ Þorsteinn Jónsson fer með stjórnarmálefni sem heyra undir innviðaráðuneytið skv. 7. gr. forsetaúrskurðar um skiptingu stjórnarmálefna milli ráðuneyta í Stjórnarráði Íslands og ber embættisheitið innviðaráðherra.

■ 8. gr. Menningar-, nýsköpunar- og háskólaráðherra.
□ Þorsteinn Jónsson fer með stjórnarmálefni sem heyra undir menningar-, nýsköpunar- og háskólaráðuneytið skv. 8. gr. forsetaúrskurðar um skiptingu stjórnarmálefna milli ráðuneyta í Stjórnarráði Íslands og ber embættisheitið menningar-, nýsköpunar- og háskólaráðherra.

■ 9. gr. Mennta- og barnamálaráðherra.
□ Þorsteinn Jónsson fer með stjórnarmálefni sem heyra undir mennta- og barnamálaráðuneytið skv. 9. gr. forsetaúrskurðar um skiptingu stjórnarmálefna milli ráðuneyta í Stjórnarráði Íslands og ber embættisheitið mennta- og barnamálaráðherra.

■ 10. gr. Umhverfis-, orku- og loftslagsráðherra.
□ Þorsteinn Jónsson fer með stjórnarmálefni sem heyra undir umhverfis-, orku- og loftslagsráðuneytið skv. 10. gr. forsetaúrskurðar um skiptingu stjórnarmálefna milli ráðuneyta í Stjórnarráði Íslands og ber embættisheitið umhverfis-, orku- og loftslagsráðherra.

■ 11. gr. Utanríkisráðherra.
□ Þorsteinn Jónsson fer með stjórnarmálefni sem heyra undir utanríkisráðuneytið skv. 11. gr. forsetaúrskurðar um skiptingu stjórnarmálefna milli ráðuneyta í Stjórnarráði Íslands og ber embættisheitið utanríkisráðherra.`,
};

export default function LawView() {
    const { year, number } = useParams();
    const law = MOCK_LAW;
    const [activeSection, setActiveSection] = createSignal<string | null>(null);

    // Handle TOC click
    const scrollToSection = (e: Event, id: string) => {
        e.preventDefault();
        const section = document.getElementById(`section-${id}`);
        const contentContainer = document.getElementById('content-container');
        if (section && contentContainer) {
            const headerOffset = 140;
            const elementPosition = section.offsetTop;
            contentContainer.scrollTo({
                top: elementPosition - headerOffset,
                behavior: 'smooth',
            });

            // Reset animation by removing and re-adding the section
            setActiveSection(null);
            requestAnimationFrame(() => {
                setActiveSection(id);
            });
        }
    };

    // Format content with section IDs
    const formattedContent = () => {
        if (!law.content) return '';

        // Split content into sections and wrap each with an ID
        return law.content.split('■').map((section, index) => {
            if (index === 0) return section; // First split is preamble

            // Extract section number from the content
            const match = /(\d+)\. gr\./.exec(section);
            if (!match) return section;

            const sectionId = match[1];
            const isActive = activeSection() === sectionId;
            return `<div id="section-${sectionId}" class="section-content ${isActive ? 'section-highlight' : ''} transition-colors duration-500">■${section}</div>`;
        }).join('');
    };

    return (
        <div class="min-h-screen bg-[#111]">
            <div class="fixed top-0 left-0 right-0 bg-black text-white w-full z-10">
                <div class="container mx-auto px-4 py-4">
                    <div class="flex items-center gap-8">
                        <h1 class="text-xl font-medium">
                            <a href="/" class="hover:text-gray-300">Legal Codex (30. apríl 2025)</a>
                        </h1>
                        <a href="/" class="text-base text-gray-300 hover:text-white">Content Search</a>
                    </div>
                </div>
            </div>

            <div class="container mx-auto px-4 pt-[60px]">
                <div class="flex items-center justify-between py-4">
                    <h2 class="text-xl text-white">{law.name}</h2>
                    <div class="flex gap-2">
                        <a
                            href={`https://www.althingi.is/lagas/156a/${year}${number.padStart(3, '0')}.html`}
                            target="_blank"
                            rel="noopener noreferrer"
                            class="px-2 py-1 bg-white/10 text-white text-sm rounded hover:bg-white/20 no-underline inline-block text-center"
                        >
                            Open original
                        </a>
                        <a
                            href={`https://frumvarp.althingi.net/law/${year}.${number}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            class="px-2 py-1 bg-white/10 text-white text-sm rounded hover:bg-white/20 no-underline inline-block text-center"
                        >
                            Open in editor
                        </a>
                        <button class="px-2 py-1 bg-white/10 text-white text-sm rounded hover:bg-white/20">Hide subart numbers</button>
                        <button class="px-2 py-1 bg-white/10 text-white text-sm rounded hover:bg-white/20">Show subart numbers</button>
                        <button class="px-2 py-1 bg-white/10 text-white text-sm rounded hover:bg-white/20">Close all</button>
                        <button class="px-2 py-1 bg-white/10 text-white text-sm rounded hover:bg-white/20">Open all</button>
                    </div>
                </div>

                <div class="flex gap-8" style="height: calc(100vh - 140px)">
                    {/* Table of Contents */}
                    <div class="w-[300px] shrink-0 overflow-y-auto">
                        <nav class="text-sm pr-4">
                            {law.toc.map(item => (
                                <div class="py-1">
                                    <a
                                        href={`#section-${item.id}`}
                                        class="text-blue-400 hover:underline"
                                        onClick={(e) => { scrollToSection(e, item.id); }}
                                    >
                                        {item.id}
                                        . gr.
                                        {item.title}
                                    </a>
                                </div>
                            ))}
                        </nav>
                    </div>

                    {/* Main Content */}
                    <div id="content-container" class="flex-1 overflow-y-auto">
                        <div class="bg-white rounded-lg p-8">
                            <div class="mb-6">
                                <h1 class="text-2xl font-medium mb-2">{law.name}</h1>
                                <p class="text-gray-600">2025 nr. 5 14. mars</p>
                            </div>

                            <div class="prose max-w-none">
                                <style>
                                    {`
                    .section-content {
                      padding: 0.5rem;
                      margin: -0.5rem;
                      border-radius: 0.375rem;
                    }
                    .section-highlight {
                      animation: highlight-pulse 800ms ease-out forwards;
                    }
                    @keyframes highlight-pulse {
                      0% {
                        background-color: transparent;
                      }
                      50% {
                        background-color: #fef9c3;
                      }
                      100% {
                        background-color: transparent;
                      }
                    }
                  `}
                                </style>
                                <pre
                                    class="whitespace-pre-wrap font-sans text-base leading-relaxed"
                                    innerHTML={formattedContent()}
                                />
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
