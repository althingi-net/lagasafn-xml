import { useParams } from '@solidjs/router';
import { createResource, For } from 'solid-js';
import { AdvertService } from '~/api';
import Header from '~/components/Header';

export default function AdvertView() {
    const { year, number } = useParams();
    const identifier = `${number}/${year}`;
    const [advert] = createResource(
        () => identifier,
        AdvertService.getAdvert,
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

            <div class="container mx-auto px-4 py-4">

                {advert() && (
                    <div class="bg-white rounded-lg p-8">
                        {advert()?.html_text && (
                            <div class="prose max-w-none legal-document">
                                <div innerHTML={advert().html_text} />
                            </div>
                        )}

                        {advert()?.affected_law_identifiers && advert().affected_law_identifiers.length > 0 && (
                            <div class="mt-8 pt-6 border-t">
                                <h3 class="text-lg font-medium mb-4">
                                    Affected Laws
                                </h3>
                                <div class="flex flex-wrap gap-2">
                                    <For each={advert().affected_law_identifiers}>
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
                        )}

                        <div class="mt-8 pt-6 border-t">
                            <a
                                href={originalUrl()}
                                target="_blank"
                                rel="noopener noreferrer"
                                class="px-4 py-2 bg-white/10 text-white text-sm rounded hover:bg-white/20 no-underline inline-block"
                            >
                                Open original
                            </a>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
