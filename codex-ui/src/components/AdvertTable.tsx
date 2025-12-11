import { For } from 'solid-js';
import { useNavigate } from '@solidjs/router';
import { AdvertEntry } from '~/api';

interface AdvertTableProps {
    adverts: AdvertEntry[];
}

export default function AdvertTable(props: AdvertTableProps) {
    const navigate = useNavigate();

    const formatDate = (dateString?: string) => {
        if (!dateString) return '-';
        try {
            const date = new Date(dateString);
            return date.toLocaleDateString('is-IS');
        }
        catch {
            return dateString;
        }
    };

    const handleRowClick = (advert: AdvertEntry) => {
        navigate(`/advert/${advert.nr}/${advert.year}`);
    };

    return (
        <div class="overflow-x-auto">
            <table class="w-full">
                <thead>
                    <tr class="border-b">
                        <th class="text-left py-2 px-4">Nr.</th>
                        <th class="text-left py-2 px-4">Year</th>
                        <th class="text-left py-2 px-4">Published Date</th>
                        <th class="text-left py-2 px-4">Description</th>
                        <th class="text-right py-2 px-4">Articles</th>
                        <th class="text-left py-2 px-4">Affected Laws</th>
                    </tr>
                </thead>
                <tbody>
                    <For each={props.adverts}>
                        {(advert: AdvertEntry) => (
                            <tr
                                class="border-b hover:bg-gray-50/50 cursor-pointer"
                                onClick={() => { handleRowClick(advert); }}
                            >
                                <td class="py-2 px-4 font-mono">{advert.nr}</td>
                                <td class="py-2 px-4">{advert.year}</td>
                                <td class="py-2 px-4">{formatDate(advert.published_date)}</td>
                                <td class="py-2 px-4">{advert.description}</td>
                                <td class="py-2 px-4 text-right">{advert.article_count}</td>
                                <td class="py-2 px-4">
                                    <div class="flex flex-wrap gap-1">
                                        <For each={advert.affected_law_identifiers}>
                                            {(lawId: string) => (
                                                <span class="px-2 py-1 bg-blue-100 text-blue-800 text-xs rounded">
                                                    {lawId}
                                                </span>
                                            )}
                                        </For>
                                    </div>
                                </td>
                            </tr>
                        )}
                    </For>
                </tbody>
            </table>
        </div>
    );
}
