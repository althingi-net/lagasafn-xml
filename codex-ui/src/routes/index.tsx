import { createSignal, createResource, createMemo } from 'solid-js';
import { LawEntry, LawIndex, LawService } from '~/api';
import Header from '~/components/Header';
import LawStats from '~/components/LawStats';
import LawTable from '~/components/LawTable';

export default function Home() {
    const [searchQuery, setSearchQuery] = createSignal('');

    const [laws] = createResource(() => LawService.listLaws());
    const [stats] = createResource(async () => ({
        totalCount: 1699,
        emptyCount: 915,
        nonEmptyCount: 784,
    }));

    // Filter laws by search query on each key press
    const filteredLaws = createMemo(() => {
        const query = searchQuery().toLowerCase().trim();
        const lawIndex = laws();

        if (!lawIndex) return [];

        const lawEntries = lawIndex.laws ?? [] as LawEntry[];

        if (!query) return lawEntries;

        return lawEntries.filter((law) => {
            const nrMatch = law.nr?.toString().toLowerCase().includes(query);
            const nameMatch = law.name?.toLowerCase().includes(query);
            return nrMatch ?? nameMatch;
        });
    });

    return (
        <div>
            <Header
                showSearch={true}
                searchValue={searchQuery()}
                onSearchChange={setSearchQuery}
            />

            <div class="container mx-auto px-4">
                <LawStats
                    totalCount={stats()?.totalCount ?? 0}
                    emptyCount={stats()?.emptyCount ?? 0}
                    nonEmptyCount={stats()?.nonEmptyCount ?? 0}
                />
                <LawTable laws={filteredLaws()} />
            </div>
        </div>
    );
}
