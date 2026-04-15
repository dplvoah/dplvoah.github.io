import charm from "astro-charm";
import path from "node:path";

const projectRoot = path.resolve(".");

export default charm({
  config: {
    lang: "zh",
    title: "dplvoah blog",
    description: "Thoughts, experiments, and open discussion.",
    author: "dplvoah",
    side: {
      title: "dplvoah",
      sub: "Thoughts, experiments, and open discussion.",
      bio: "A practical blog space for writing, experimenting, and iterating in public.",
      navHome: {
        title: "Home",
        link: "/",
      },
      footer: [
        {
          title: "GitHub",
          link: "https://github.com/dplvoah",
          icon: "simple-icons:github",
        },
        {
          title: "Repo",
          link: "https://github.com/dplvoah/dplvoah.github.io",
          icon: "solar:code-bold-duotone",
        },
      ],
    },
    giscus: {
      repo: "dplvoah/dplvoah.github.io",
      repoId: "R_kgDOR8zCyw",
      category: "Comments",
      categoryId: "DIC_kwDOR8zCy84C6Xkq",
      mapping: "pathname",
      strict: false,
      reactions: true,
      emitMetadata: true,
      inputPosition: "bottom",
      theme: {
        light: "light",
        dark: "dark",
      },
    },
  },
  pages: {
    "/": false,
    "/posts/[...slug]": false,
  },
  overrides: {
    custom: {
      CustomPostHeaderBottom: path.join(projectRoot, "src/components/charm/CustomPostHeaderBottom.astro"),
      CustomPostFooterTop: path.join(projectRoot, "src/components/charm/CustomPostFooterTop.astro"),
    },
  },
});
