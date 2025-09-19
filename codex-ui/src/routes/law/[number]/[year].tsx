import { useParams, A } from '@solidjs/router';
import { createSignal, createResource, onMount, createMemo } from 'solid-js';
import { LawService } from '~/api';

export default function LawView() {
    const { year, number } = useParams();
    const identifier = `${number}/${year}`;
    const [law] = createResource(() => {
        return identifier;
    }, LawService.getLaw);

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
        if (!law()?.content) return '';

        // Split content into sections and wrap each with an ID
        return law().content.split('■').map((section, index) => {
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
                    <h2 class="text-xl text-white">{law()?.name}</h2>
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
                            {law()?.chapters.map(chapter => (
                                <div class="py-1">
                                    <a
                                        href={`#section-${chapter.nr}`}
                                        class="text-blue-400 hover:underline"
                                        onClick={(e) => { scrollToSection(e, chapter.nr); }}
                                    >
                                        {chapter.nr_title}
                                    </a>
                                </div>
                            ))}
                        </nav>
                    </div>

                    {/* Main Content */}
                    <div id="content-container" class="flex-1 overflow-y-auto">
                        <div class="bg-white rounded-lg p-8">
                            <div class="mb-6">
                                <h1 class="text-2xl font-medium mb-2">{law()?.name}</h1>
                                <p class="text-gray-600">2025 nr. 5 14. mars</p>
                            </div>

                            <div class="prose max-w-none">
                                <div innerHTML={law()?.html_text} />
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
