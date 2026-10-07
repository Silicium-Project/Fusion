// Types shared by the message catalogs (`fr.ts` is the reference: `en.ts`
// and `de.ts` must have exactly the same keys, checked by TypeScript).

/** Values inserted in a message: `{count}`, `{name}`… */
export type MessageParams = Record<string, string | number>;

/** A message: text with `{placeholders}`, or a function for plurals. */
export type MessageFunction = (params: MessageParams) => string;

/** The shape of a catalog, with the French texts widened to `string`. */
export type Catalog<T> = T extends MessageFunction
  ? MessageFunction
  : T extends string
    ? string
    : T extends readonly (infer Item)[]
      ? Catalog<Item>[]
      : { [Key in keyof T]: Catalog<T[Key]> };

/** `count` of the params, as a number. */
export const countOf = (params: MessageParams): number => Number(params.count) || 0;
