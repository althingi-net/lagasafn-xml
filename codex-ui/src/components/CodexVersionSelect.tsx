import { createResource, For } from 'solid-js';
import { LawService } from '~/api';

interface CodexVersionSelectProps {
    value: string | undefined;
    onInput: (value: string | undefined) => void;
}

export default function CodexVersionSelect(props: CodexVersionSelectProps) {
    const [codexVersions] = createResource(() =>
        LawService.listCodexVersions(),
    );

    return (
        <select
            value={props.value ?? ''}
            onInput={(e) => {
                const value = e.currentTarget.value;
                props.onInput(value || undefined);
            }}
            disabled={codexVersions.loading}
            class="px-3 py-1 bg-white/10 text-white border border-white/20 rounded focus:outline-none focus:border-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
        >
            {!codexVersions.loading && !codexVersions.error && (
                <>
                    <For each={codexVersions() ?? []}>
                        {version => (
                            <option
                                value={version}
                                selected={version === props.value}
                                class="bg-gray-800 text-white"
                            >
                                {version}
                            </option>
                        )}
                    </For>
                </>
            )}
        </select>
    );
}
