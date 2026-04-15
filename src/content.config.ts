import { defineCollection } from "astro:content";
import { glob } from "astro/loaders";
import { z } from "astro/zod";
import { collections as charmCollections } from "astro-charm/content";

const posts = defineCollection({
  loader: glob({ base: "./src/content/blog", pattern: "**/*.{md,mdx}" }),
  schema: ({ image }) =>
    z
      .object({
        title: z.string(),
        description: z.string().optional(),
        published: z.coerce.date().optional(),
        pubDate: z.coerce.date().optional(),
        updated: z.coerce.date().optional(),
        category: z.string().optional(),
        group: z.string().optional(),
        author: z.string().optional(),
        tags: z.array(z.string().min(1)).default([]),
        image: image()
          .optional()
          .or(
            z.object({
              skip: z.string(),
            }),
          ),
        discussionId: z.string().optional(),
        draft: z.boolean().default(false),
        hidden: z.boolean().default(false),
      })
      .refine((data) => data.published || data.pubDate, {
        message: "Either published or pubDate is required.",
      })
      .transform((data) => ({
        ...data,
        published: data.published ?? data.pubDate ?? new Date("1970-01-01"),
        category: data.category ?? data.group ?? "general",
        group: data.group ?? data.category ?? "general",
        author: data.author ?? "unknown",
      })),
});

export const collections = {
  posts,
  specials: charmCollections.specials,
};
