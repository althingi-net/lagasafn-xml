import stylistic from '@stylistic/eslint-plugin';
import importPlugin from 'eslint-plugin-import';
import tseslint from 'typescript-eslint';
import solid from 'eslint-plugin-solid';

export default tseslint.config(
    {
        ignores: [
            "dist",
            "node_modules",
            "eslint.config.js",
            "app.config.ts",
            "src/api/**/*"
        ]
    },
    tseslint.configs.strictTypeChecked,
    tseslint.configs.stylisticTypeChecked,
    stylistic.configs.recommended,
    importPlugin.flatConfigs.recommended,
    importPlugin.flatConfigs.typescript,
    {
        settings: {
            'import/resolver': {
                typescript: {
                    alwaysTryTypes: true,
                    project: './tsconfig.json',
                },
                node: true,
            },
        },
    },
    {
        languageOptions: {
            parserOptions: {
                projectService: true,
                tsconfigRootDir: import.meta.dirname,
            },
        },
    },
    {
        plugins: {
            '@stylistic': stylistic,
            'solid/typescript': solid,
        },
        rules: {
            // Stylistic rules
            '@stylistic/quotes': ['error', 'single'],
            '@stylistic/semi': ['error', 'always'],
            '@stylistic/indent': ['error', 4],
            '@stylistic/member-delimiter-style': ['error', {
                multiline: { delimiter: 'semi', requireLast: true },
                singleline: { delimiter: 'semi', requireLast: false },
            }],

            // JSX Stylistic rules
            '@stylistic/jsx-indent-props': ['error', 4],
            '@typescript-eslint/naming-convention': [
                'error',
                {
                    selector: 'variable',
                    format: ['camelCase', 'UPPER_CASE', 'PascalCase'],
                    leadingUnderscore: 'forbid',
                    trailingUnderscore: 'forbid',
                },
                {
                    selector: 'function',
                    format: ['camelCase', 'PascalCase'],
                    leadingUnderscore: 'forbid',
                    trailingUnderscore: 'forbid',
                },
            ],

            // Developer Experience
            '@typescript-eslint/restrict-template-expressions': [
                'error',
                { allowNumber: true, allowNever: true, allowNullish: true, allowAny: true }
            ],
            '@typescript-eslint/require-await': 'off',
            '@typescript-eslint/unbound-method': 'off',

            // Disable rules already checked by TypeScript
            '@typescript-eslint/no-undef': 'off',
            '@typescript-eslint/no-unused-vars': 'off',
            '@typescript-eslint/no-dupe-class-members': 'off',
            '@typescript-eslint/no-redeclare': 'off',
            '@typescript-eslint/no-loss-of-precision': 'off',

            // Solid.js requires default exports for pages
            'import/no-default-export': 'off',
        }
    },
    {
        // Test file specific rules
        files: ['**/*.test.ts', '**/*.test.tsx', '**/*.spec.ts', '**/*.spec.tsx'],
        rules: {
            '@typescript-eslint/no-explicit-any': 'off',
            '@typescript-eslint/no-confusing-void-expression': 'off',
            '@typescript-eslint/no-unsafe-member-access': 'off',
            '@typescript-eslint/no-unsafe-assignment': 'off',
            '@typescript-eslint/no-unsafe-return': 'off',
            '@typescript-eslint/no-unsafe-call': 'off',
            '@typescript-eslint/no-unsafe-argument': 'off',
            '@typescript-eslint/no-empty-function': 'off',
        },
    }
);
