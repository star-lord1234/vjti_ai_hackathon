/**
 * Maharashtra GR structure rules — mirrors backend/data/gr_template_structure.json
 * and the detection heuristics in parser/section_locator.py (frontend-only reference).
 */

export interface GrTemplateRule {
  order: number;
  id: string;
  label: string;
  labelMr: string;
  required: boolean;
  description: string;
  detectionHints: string[];
  severityMissing: "high" | "medium" | "low";
  severityMisordered: "high" | "medium" | "low";
}

export const GR_TEMPLATE_RULES: GrTemplateRule[] = [
  {
    order: 1,
    id: "header_block",
    label: "Header / document-type block",
    labelMr: "शीर्षक / दस्तऐवज प्रकार",
    required: true,
    description:
      "Opening block identifying the state, department, GR number, and exact issue date at the top of the document.",
    detectionHints: [
      "महाराष्ट्र शासन or GOVERNMENT OF MAHARASHTRA",
      "Department name: उच्च व तंत्र शिक्षण विभाग, वित्त विभाग, etc.",
      "GR number and date near the top-center or right side",
    ],
    severityMissing: "high",
    severityMisordered: "medium",
  },
  {
    order: 2,
    id: "subject_line",
    label: "Subject line",
    labelMr: "विषय ओळ",
    required: true,
    description:
      "A clear subject or short title describing the matter under consideration.",
    detectionHints: [
      "विषय: followed by the policy subject text",
      "Title lines appearing before the main decision body",
    ],
    severityMissing: "high",
    severityMisordered: "high",
  },
  {
    order: 3,
    id: "preamble_section",
    label: "Preamble / background section",
    labelMr: "प्रस्तावना / पार्श्वभूमी",
    required: true,
    description:
      "Background-to-order narrative linking context, references, and the final resolution in the sequence: Background → Reference → Resolution.",
    detectionHints: [
      "प्रस्तावना: or Preamble:",
      "Context paragraphs explaining why the decision is being taken",
      "Reference and resolution follow in the same narrative flow",
    ],
    severityMissing: "high",
    severityMisordered: "high",
  },
  {
    order: 4,
    id: "references_section",
    label: "References (वाचा) section",
    labelMr: "वाचा / संदर्भ",
    required: false,
    description:
      "Lists prior GRs, circulars, or files being cited. Useful for formal traceability, but optional in some drafts.",
    detectionHints: [
      "Section headed वाचा, बाचा, संदर्भ, or Reference",
      "Numbered reference items with dates or GR numbers",
    ],
    severityMissing: "low",
    severityMisordered: "low",
  },
  {
    order: 5,
    id: "operative_section",
    label: "Operative / decision paragraph(s)",
    labelMr: "शासन निर्णय / ऑपरेटिव्ह परिच्छेद",
    required: true,
    description:
      "The binding decision text — approvals, sanctions, directives, or numbered operative clauses that implement the resolution.",
    detectionHints: [
      "शासन निर्णय : (not just the header line)",
      "यान्वये … मंजूर operative formula",
      "Numbered clauses: कलम / Section / Clause",
    ],
    severityMissing: "high",
    severityMisordered: "medium",
  },
  {
    order: 6,
    id: "financial_sanction_block",
    label: "Financial sanction / funding block",
    labelMr: "वित्त मान्यता / निधी समभाग",
    required: true,
    description:
      "Explicit approval or sanction noting the financial implication, source of funds, or amount being released/allocated.",
    detectionHints: [
      "निधी वितरीत करण्यास मान्यता",
      "सदर खर्च ... लेखाशिर्षाखाली / अर्थसंकल्पीय तरतूद",
      "Mention of financial approval, sanction, or release of funds",
    ],
    severityMissing: "high",
    severityMisordered: "medium",
  },
  {
    order: 7,
    id: "budget_head",
    label: "Budget head / accounting head",
    labelMr: "अर्थसंकल्प / लेखाशिर्ष",
    required: true,
    description:
      "The specific budget or accounting head for the sanctioned amount, e.g. 2054-00-101-02 or the equivalent account code wording.",
    detectionHints: [
      "मागणी क्रमांक / लेखाशिर्ष / अर्थसंकल्प",
      "Code format like 2054-00-101-02 or similar budget-head phrasing",
      "Expense head linked to the sanctioned amount",
    ],
    severityMissing: "high",
    severityMisordered: "medium",
  },
  {
    order: 8,
    id: "signatory_block",
    label: "Signatory block",
    labelMr: "स्वाक्षरी खंड",
    required: true,
    description:
      "Closing signature block with official designation, department name, and forwarding list where relevant.",
    detectionHints: [
      "(सचिव) or Secretary designation near document end",
      "Department name below the signatory line",
      "Distribution / CC list after the signature block",
    ],
    severityMissing: "high",
    severityMisordered: "medium",
  },
];

export const GR_TEMPLATE_SCORING_NOTE =
  "Template accuracy scores required sections in this order: full credit when present and correctly ordered, half credit when present but misordered, zero when missing.";
