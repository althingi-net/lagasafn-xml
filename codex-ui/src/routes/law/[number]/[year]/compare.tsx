import { useParams, useSearchParams, A } from '@solidjs/router';
import { createResource, createMemo } from 'solid-js';
import { LawService } from '~/api';
import Header from '~/components/Header';
import LawVersionSelect from '~/components/LawVersionSelect';
import '~/law.css';
import { htmlDiff } from '@benedicte/html-diff';

export default function LawCompare() {
    const { year, number } = useParams();
    const [searchParams, setSearchParams] = useSearchParams();
    const identifier = `${number}/${year}`;

    // Get versions from query params
    const version = createMemo(() => searchParams.version as string | undefined);
    const compareWith = createMemo(() => searchParams.compareWith as string | undefined);

    // Fetch both law versions
    const [law1] = createResource(
        () => [identifier, version()] as const,
        ([id, v]) => LawService.getLaw(id, v),
    );

    const [law2] = createResource(
        () => [identifier, compareWith()] as const,
        ([id, v]) => LawService.getLaw(id, v),
    );

    // Handle version changes
    const handleVersion1Change = (newVersion: string) => {
        if (newVersion) {
            setSearchParams({ ...searchParams, version: newVersion });
        }
        else {
            const rest = { ...searchParams };
            delete rest.version;
            setSearchParams(rest);
        }
    };

    const handleVersion2Change = (newVersion: string) => {
        if (newVersion) {
            setSearchParams({ ...searchParams, compareWith: newVersion });
        }
        else {
            const rest = { ...searchParams };
            delete rest.compareWith;
            setSearchParams(rest);
        }
    };

    const availableVersions = createMemo(() => {
        return law1()?.versions ?? law2()?.versions ?? [];
    });

    // Create unified diff HTML showing both versions with changes highlighted
    const diffHtml = createMemo((): string | null => {
        if (law1.error || law2.error) {
            return null;
        }
        const l1 = law1();
        const l2 = law2();
        if (!l1 || !l2) {
            return null;
        }

        return htmlDiff(l1.html_text, l2.html_text);
    });

    // Calculate diff statistics
    const diffStats = createMemo(() => {
        const html = diffHtml();
        const l1 = law1();
        if (!html || !l1) {
            return null;
        }

        // Count additions (ins tags) and deletions (del tags)
        const insMatches = html.match(/<ins[^>]*>/gi) ?? [];
        const delMatches = html.match(/<del[^>]*>/gi) ?? [];

        // Count text content in additions and deletions
        const insTextMatches = html.match(/<ins[^>]*>([^<]*)<\/ins>/gi) ?? [];
        const delTextMatches = html.match(/<del[^>]*>([^<]*)<\/del>/gi) ?? [];

        // Calculate total text length in changes
        let insTextLength = 0;
        let delTextLength = 0;

        insTextMatches.forEach((match) => {
            const textMatch = /<ins[^>]*>([^<]*)<\/ins>/i.exec(match);
            if (textMatch?.[1]) {
                insTextLength += textMatch[1].trim().length;
            }
        });

        delTextMatches.forEach((match) => {
            const textMatch = /<del[^>]*>([^<]*)<\/del>/i.exec(match);
            if (textMatch?.[1]) {
                delTextLength += textMatch[1].trim().length;
            }
        });

        // Get total text length from original for percentage calculation
        const totalTextLength = l1.html_text ? l1.html_text.replace(/<[^>]*>/g, '').trim().length : 0;

        const additions = insMatches.length;
        const deletions = delMatches.length;
        const totalChanges = additions + deletions;
        const changePercentage = totalTextLength > 0
            ? ((insTextLength + delTextLength) / totalTextLength * 100).toFixed(1)
            : '0';

        return {
            additions,
            deletions,
            totalChanges,
            insTextLength,
            delTextLength,
            changePercentage,
        };
    });

    return (
        <div class="min-h-screen bg-[#111]">
            <Header />

            <div class="container mx-auto px-4">
                <div class="flex items-center justify-between py-4">
                    <div class="flex items-center gap-4">
                        <A
                            href={`/law/${number}/${year}${version() ? `?version=${version()}` : ''}`}
                            class="text-white hover:text-blue-400 no-underline"
                        >
                            ← Back
                        </A>
                        <h2 class="text-xl text-white">
                            Compare Law
                            {' '}
                            {identifier}
                        </h2>
                    </div>
                    <div class="flex gap-2 items-center">
                        {/* Version 1 selector */}
                        <label class="text-white text-sm">Version 1:</label>
                        <LawVersionSelect
                            value={version() ?? ''}
                            onInput={handleVersion1Change}
                            versions={availableVersions()}
                            disabled={law1.loading || law2.loading}
                        />

                        {/* Version 2 selector */}
                        <label class="text-white text-sm ml-4">Version 2:</label>
                        <LawVersionSelect
                            value={compareWith() ?? ''}
                            onInput={handleVersion2Change}
                            versions={availableVersions()}
                            disabled={law1.loading || law2.loading}
                        />
                    </div>
                </div>

                {/* Unified diff view */}
                <div class="overflow-y-auto" style="height: calc(100vh - 140px)">
                    <div class="bg-white rounded-lg p-8">
                        <div class="mb-4 border-b pb-2">
                            <h3 class="text-lg font-medium">
                                {law1()?.name ?? 'Loading...'}
                            </h3>
                            <p class="text-sm text-gray-600">
                                Comparing:
                                {' '}
                                {version()}
                                {' '}
                                vs
                                {' '}
                                {compareWith()}
                            </p>
                            {diffStats() && (
                                <div class="mt-4 p-4 bg-gray-50 rounded-lg border border-gray-200">
                                    <h4 class="text-sm font-semibold text-gray-700 mb-2">Change Summary</h4>
                                    <div class="grid grid-cols-4 gap-4 text-sm">
                                        <div>
                                            <span class="text-gray-600">Additions:</span>
                                            {' '}
                                            <span class="font-semibold text-green-600">
                                                {diffStats()?.additions ?? 0}
                                            </span>
                                        </div>
                                        <div>
                                            <span class="text-gray-600">Deletions:</span>
                                            {' '}
                                            <span class="font-semibold text-red-600">
                                                {diffStats()?.deletions ?? 0}
                                            </span>
                                        </div>
                                        <div>
                                            <span class="text-gray-600">Total Changes:</span>
                                            {' '}
                                            <span class="font-semibold text-blue-600">
                                                {diffStats()?.totalChanges ?? 0}
                                            </span>
                                        </div>
                                        <div>
                                            <span class="text-gray-600">Change %:</span>
                                            {' '}
                                            <span class="font-semibold text-gray-800">
                                                {diffStats()?.changePercentage ?? '0'}
                                                %
                                            </span>
                                        </div>
                                    </div>
                                </div>
                            )}
                        </div>
                        <div class="prose max-w-none legal-document">
                            {diffHtml()
                                ? (
                                    <div innerHTML={diffHtml() ?? ''} />
                                )
                                : law1()?.html_text
                                    ? (
                                        <div innerHTML={law1()?.html_text ?? ''} />
                                    )
                                    : (
                                        <p class="text-gray-500">Loading...</p>
                                    )}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
