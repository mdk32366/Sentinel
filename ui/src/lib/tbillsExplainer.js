/**
 * Plain-language T-bills explainer copy for ABOUT (D-0092).
 *
 * Lives in lib/ so G1–G3 can hold the myth phrases, the eighth-grade ceiling
 * and the no-data rule shut — the same pattern as dataSources.js (F-0096).
 * No React, no hooks, no fetch. The only figures are a labelled example.
 */

export const TBILLS_EXPLAINER = {
  title: "START HERE — HOW T-BILLS WORK",
  sections: [
    {
      id: "what",
      heading: "What is a T-bill?",
      paragraphs: [
        "A Treasury bill, or T-bill, is a short IOU from the US government.",
        "It lasts a few weeks or up to one year.",
        "You pay less than the face amount today. When the bill comes due, the government pays you the full face amount.",
        "Example: you pay $990 now and get $1,000 back in six months. The $10 gap is your interest.",
        "Other countries borrow the same way. Their bills just have different names.",
      ],
    },
    {
      id: "how",
      heading: "How does a government use them?",
      paragraphs: [
        "A government needs cash every day. It has bills to pay, and tax money comes in later and in lumps.",
        "So it sells T-bills at an auction. Banks, funds, companies, people and other countries' central banks offer to buy. The government sells to the best offers and gets the cash now.",
        "When a bill comes due, the government pays it off. Most of the time it pays with money from selling new bills. This is called rolling over.",
        "Cash now. Pay later. Then do it again.",
      ],
    },
    {
      id: "price",
      heading: "Why does the price change?",
      paragraphs: [
        "A bill always pays the same face amount at the end. Only the price you pay today changes.",
        "Price and yield sit on a seesaw. Yield is what you earn, as a yearly percent.",
        "Pay less for the same $1,000 and you earn more, so the yield goes up. Pay more and you earn less, so the yield goes down.",
        "News moves the seesaw. If people think rates will rise, old bills must get cheaper to keep up with new ones. If people get scared and want a safe place for cash, they buy bills, and prices go up.",
        "T-bills are short, so their prices move only a little. Long bonds move much more.",
      ],
    },
  ],
  myth: {
    id: "myth",
    chip: "MYTH vs FACT",
    heading: "Cashing a T-bill is not buying oil",
    paragraphs: [
      "Myth: when a country cashes in its T-bills, it is buying oil.",
      "Fact: cashing in a T-bill gets you dollars back. That is all it does. It is not the same as buying crude oil.",
      "Oil-selling countries are mostly paid in dollars. They often park those dollars in T-bills until they need to spend them.",
      "When a bill comes due or is sold, the dollars are free again. They can then buy oil, pay workers, build roads or buy another bill. That spending is a separate step.",
      "Sentinel can see a country's Treasury holdings go down. It cannot see what the dollars bought next.",
    ],
  },
  cheatSheet: {
    summary: "Cheat sheet: which way do yields move?",
    headers: ["When this happens…", "Bill prices", "Yields"],
    rows: [
      ["People expect the Fed to raise rates", "Down", "Up"],
      ["People expect the Fed to cut rates", "Up", "Down"],
      ["Scary news, and people want somewhere safe", "Up", "Down"],
      ["Lots of new bills for sale, or big sellers", "Down", "Up"],
      ["Worry the government could pay late, like a debt-limit fight", "Down", "Up"],
    ],
    note: "Usually, not always. Price and yield always move in opposite directions. The news only decides which way.",
  },
};
