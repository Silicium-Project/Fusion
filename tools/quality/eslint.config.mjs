import ts from 'typescript-eslint';
import vue from 'eslint-plugin-vue';
import vueParser from 'vue-eslint-parser';
// Small correctness baseline; formatting is handled by Prettier. Type errors
// are checked by the component's compiler, with its own pinned dependencies.
export default [
  { ignores: ['**/node_modules/**', '**/dist/**', '**/.nuxt/**', '**/.output/**', '**/target/**'] },
  {
    files: ['**/*.ts', '**/*.mts', '**/*.mjs'],
    languageOptions: { parser: ts.parser, ecmaVersion: 2023, sourceType: 'module' },
    rules: {
      'constructor-super': 'error',
      'no-async-promise-executor': 'error',
      'no-constant-binary-expression': 'error',
      'no-dupe-args': 'error',
      'no-duplicate-case': 'error',
      'no-func-assign': 'error',
      'no-import-assign': 'error',
      'no-promise-executor-return': 'error',
      'no-unreachable': 'error',
      'valid-typeof': 'error',
    },
  },
  {
    files: ['**/*.vue'],
    languageOptions: {
      parser: vueParser,
      parserOptions: { parser: ts.parser, extraFileExtensions: ['.vue'] },
    },
    plugins: { vue },
    rules: {
      'vue/no-dupe-keys': 'error',
      'vue/no-duplicate-attributes': 'error',
      'vue/no-parsing-error': 'error',
      'vue/valid-v-for': 'error',
      'vue/valid-v-if': 'error',
      'vue/valid-v-else': 'error',
      'vue/valid-v-model': 'error',
    },
  },
];
