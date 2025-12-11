import {
    createSignal,
    createResource,
    createMemo,
    createEffect,
} from 'solid-js';
import { AdvertService, AdvertEntry } from '~/api';
import AdvertTable from '~/components/AdvertTable';
import CodexVersionSelect from '~/components/CodexVersionSelect';

export default function AdvertList() {
    const [codexVersion, setCodexVersion] = createSignal<string | undefined>();

    // Fetch adverts based on codex version (undefined means use API default)
    // Always run the resource - use a computed key that always has a value
    const codexVersionKey = createMemo(() => codexVersion() ?? 'default');
    const [advertIndex] = createResource(
        codexVersionKey,
        version => AdvertService.listAdverts(version === 'default' ? undefined : version),
    );

    // Set default codex version from the response
    createEffect(() => {
        const index = advertIndex();
        if (index?.info?.codex_version) {
            setCodexVersion(index.info.codex_version);
        }
    });

    // Get all adverts
    const adverts = createMemo(() => {
        const index = advertIndex();
        if (!index) return [];
        return (index.adverts ?? []) as AdvertEntry[];
    });

    return (
        <div>
            <div class="container mx-auto px-4 py-4">
                <div class="mb-4 flex items-center gap-4">
                    <label for="codex-version" class="text-white font-medium">
                        Codex Version:
                    </label>
                    <CodexVersionSelect
                        value={codexVersion()}
                        onInput={setCodexVersion}
                    />
                    {advertIndex.loading && <span class="text-white/70">Loading...</span>}
                    {advertIndex.error && (
                        <span class="text-red-400">Error loading adverts</span>
                    )}
                </div>

                {advertIndex()?.info && (
                    <div class="mb-4 text-white/70 text-sm">
                        <p>
                            Total Adverts:
                            {' '}
                            <span class="font-semibold">
                                {advertIndex()?.info?.total_count}
                            </span>
                        </p>
                    </div>
                )}

                <AdvertTable adverts={adverts()} />
            </div>
        </div>
    );
}
