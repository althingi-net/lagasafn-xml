import { useParams } from '@solidjs/router';
import { createSignal, createResource, createEffect } from 'solid-js';
import { LawService } from '~/api';
import Header from '~/components/Header';

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

    // Make sections togglable
    const makeTogglable = (element: Element) => {
        // Find a handle to control toggling. If element has no name, try nr-title.
        let toggleButton = element.querySelector('name');
        if (!toggleButton) {
            toggleButton = element.querySelector('nr-title');
        }

        if (toggleButton) {
            // Add toggle button class and attributes
            (toggleButton as HTMLElement).classList.add('toggle-button');
            toggleButton.setAttribute('data-state', 'open');
            toggleButton.setAttribute('data-toggle-id', element.getAttribute('nr') || '');

            // Add click handler
            toggleButton.addEventListener('click', () => {
                const state = toggleButton?.getAttribute('data-state');
                const subject = element;

                if (state === 'closed') {
                    // Show all children
                    const children = subject.children;
                    for (let i = 0; i < children.length; i++) {
                        children[i].classList.remove('toggle-hidden');
                    }
                    toggleButton?.setAttribute('data-state', 'open');
                } else {
                    // Hide all children except toggle button, img, nr-title, and name
                    const children = subject.children;
                    for (let i = 0; i < children.length; i++) {
                        const child = children[i];
                        if (!child.classList.contains('toggle-button') &&
                            child.tagName.toLowerCase() !== 'img' &&
                            child.tagName.toLowerCase() !== 'nr-title' &&
                            child.tagName.toLowerCase() !== 'name') {
                            child.classList.add('toggle-hidden');
                        }
                    }
                    toggleButton?.setAttribute('data-state', 'closed');
                }
            });
        }
    };

    // Apply toggle functionality after content is loaded
    const applyToggleFunctionality = () => {
        // Wait for the next tick to ensure content is rendered
        setTimeout(() => {
            const contentContainer = document.querySelector('.legal-document');
            if (contentContainer) {
                // Make superchapters togglable
                const superchapters = contentContainer.querySelectorAll('superchapter');
                superchapters.forEach(makeTogglable);

                // Make chapters togglable
                const chapters = contentContainer.querySelectorAll('chapter');
                chapters.forEach(makeTogglable);

                // Make articles togglable
                const articles = contentContainer.querySelectorAll('art');
                articles.forEach(makeTogglable);
            }
        }, 0);
    };

    // Close all sections
    const closeAllSections = () => {
        const contentContainer = document.querySelector('.legal-document');
        if (contentContainer) {
            const toggleButtons = contentContainer.querySelectorAll('.toggle-button[data-state="open"]');
            toggleButtons.forEach(button => {
                const event = new MouseEvent('click', {
                    view: window,
                    bubbles: true,
                    cancelable: true
                });
                button.dispatchEvent(event);
            });
        }
    };

    // Open all sections
    const openAllSections = () => {
        const contentContainer = document.querySelector('.legal-document');
        if (contentContainer) {
            const toggleButtons = contentContainer.querySelectorAll('.toggle-button[data-state="closed"]');
            toggleButtons.forEach(button => {
                const event = new MouseEvent('click', {
                    view: window,
                    bubbles: true,
                    cancelable: true
                });
                button.dispatchEvent(event);
            });
        }
    };

    // Apply toggle functionality when law content is loaded
    createEffect(() => {
        if (law() && law()?.html_text) {
            // Wait for the next tick to ensure content is rendered
            setTimeout(() => {
                applyToggleFunctionality();
            }, 0);
        }
    });

    return (
        <div class="min-h-screen bg-[#111]">
            <Header />

            <div class="container mx-auto px-4">
                <div class="flex items-center justify-between py-4">
                    <h2 class="text-xl text-white">&nbsp;</h2>
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
                        <button class="px-2 py-1 bg-white/10 text-white text-sm rounded hover:bg-white/20" onClick={closeAllSections}>Close all</button>
                        <button class="px-2 py-1 bg-white/10 text-white text-sm rounded hover:bg-white/20" onClick={openAllSections}>Open all</button>
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

                            <div class="prose max-w-none legal-document">
                                <div innerHTML={law()?.html_text} />
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
