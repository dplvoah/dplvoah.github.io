import { defineCollection } from "astro:content";
import { glob } from "astro/loaders";
import { z } from "astro/zod";

const blog = defineCollection({
  loader: glob({ base: "./src/content/blog", pattern: "**/*.{md,mdx}" }),
  schema: z.object({
    title: z.string(),
    description: z.string().optional(),
    pubDate: z.coerce.date(),
    author: z.enum(["dplvoah", "imlevv"]),
    tags: z.array(z.string().min(1)),
    group: z.string().min(1),
    discussionId: z.string().optional(),
    draft: z.boolean().optional(),
  }),
});

export const collections = {
  blog,
};
