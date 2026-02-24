import { useParams } from '@solidjs/router';
import { createResource, For, Show } from 'solid-js';
import { AdvertService } from '~/api';
import Header from '~/components/Header';

export default function AdvertView() {
    const { year, number } = useParams();
    const identifier = `${number}/${year}`;
    const [advert] = createResource(
        () => identifier,
        AdvertService.getAdvert,
    );
    const [intentDetails] = createResource(
        () => identifier,
        AdvertService.getAdvertIntents,
    );

    const formatDate = (dateString?: string | null) => {
        if (!dateString) return '-';
        try {
            const date = new Date(dateString);
            return date.toLocaleDateString('is-IS');
        }
        catch {
            return dateString;
        }
    };

    const originalUrl = () => {
        const recordId = advert()?.record_id;
        if (!recordId) return '#';
        return `https://www.stjornartidindi.is/Advert.aspx?RecordID=${recordId}`;
    };

    return (
        <div class="min-h-screen bg-[#111]">
            <Header />
            <div class="container mx-auto px-4">
                <div class="flex items-center justify-end py-4">
                    <div class="flex gap-2 items-center">
                        <a
                            href={originalUrl()}
                            target="_blank"
                            rel="noopener noreferrer"
                            class="px-2 py-1 bg-white/10 text-white text-sm rounded hover:bg-white/20 no-underline inline-block text-center"
                        >
                            Open original
                        </a>
                    </div>
                </div>

                <div class="flex gap-8" style="height: calc(100vh - 140px)">
                    <div class="w-[300px] shrink-0 overflow-y-auto">
                        <Show when={advert()?.affected_law_identifiers && (advert()?.affected_law_identifiers.length ?? 0) > 0}>
                            <div class="">
                                <h3 class="text-lg font-medium mb-4">
                                    Affected Laws
                                </h3>
                                <div class="flex flex-wrap gap-2">
                                    <For each={advert()?.affected_law_identifiers ?? []}>
                                        {(lawId) => {
                                            const [nr, year] = lawId.split('/');
                                            return (
                                                <a
                                                    href={`/law/${nr}/${year}`}
                                                    class="px-3 py-1 bg-blue-100 text-blue-800 text-sm rounded hover:bg-blue-200"
                                                >
                                                    {lawId}
                                                </a>
                                            );
                                        }}
                                    </For>
                                </div>
                            </div>
                        </Show>
                        <Show when={intentDetails()}>
                            {details => (
                                <div class="mt-12 border-t pt-8">
                                    <div class="mb-6">
                                        <h2 class="text-xl font-medium mb-2">Intent Changes</h2>
                                        <p class="text-sm text-gray-600">
                                            Codex Version:
                                            {' '}
                                            {details().codex_version}
                                            {' → '}
                                            {details().next_codex_version}
                                            {' '}
                                            (Enacted:
                                            {' '}
                                            {formatDate(details().enact_date)}
                                            )
                                        </p>
                                    </div>
                                    <For each={details().laws}>
                                        {law => (
                                            <div class="mb-8">
                                                <h3 class="text-lg font-medium mb-4">
                                                    Law
                                                    {' '}
                                                    {law.identifier}
                                                </h3>
                                                <For each={law.intents}>
                                                    {intent => (
                                                        <div class="mb-6 border-l-4 border-blue-500 pl-4">
                                                            <div class="mb-2">
                                                                <span class="font-medium">
                                                                    Intent
                                                                    {' '}
                                                                    {intent.nr}
                                                                </span>
                                                                {' '}
                                                                <span class="text-sm text-gray-600">
                                                                    (
                                                                    {intent.action}
                                                                    )
                                                                </span>
                                                            </div>
                                                            <div class="grid grid-cols-2 gap-4 mt-4">
                                                                <Show when={intent.applied}>
                                                                    {applied => (
                                                                        <div>
                                                                            <div class="text-sm font-medium mb-2 text-green-700">
                                                                                Applied Version
                                                                            </div>
                                                                            <div class="p-3 rounded text-sm border border-green-200">
                                                                                <pre class="whitespace-pre-wrap font-mono text-xs">
                                                                                    {applied().text}
                                                                                </pre>
                                                                            </div>
                                                                        </div>
                                                                    )}
                                                                </Show>
                                                                <Show when={intent.next}>
                                                                    {next => (
                                                                        <div>
                                                                            <div class="text-sm font-medium mb-2 text-blue-700">
                                                                                Next Codex Version
                                                                            </div>
                                                                            <div class="p-3 rounded text-sm border border-blue-200">
                                                                                <pre class="whitespace-pre-wrap font-mono text-xs">
                                                                                    {next().text}
                                                                                </pre>
                                                                            </div>
                                                                        </div>
                                                                    )}
                                                                </Show>
                                                            </div>
                                                        </div>
                                                    )}
                                                </For>
                                            </div>
                                        )}
                                    </For>
                                </div>
                            )}
                        </Show>

                    </div>
                    <div id="content-container" class="flex-1 overflow-y-auto">
                        <div class="bg-white rounded-lg p-8">
                            <div class="mb-6">
                                <h1 class="text-2xl font-medium mb-2 text-[#242424]">
                                    LÖG
                                    {' '}
                                    {advert()?.description}
                                </h1>
                                <p class="text-gray-600">
                                    Nr.
                                    {' '}
                                    {advert()?.identifier}
                                    {' '}
                                    {formatDate(advert()?.published_date)}
                                </p>
                            </div>

                            <div class="prose max-w-none legal-document">
                                <div innerHTML={advert()?.original_html_text ?? ''} />
                            </div>
                        </div>
                    </div>

                </div>
            </div>
        </div>
    );
}
