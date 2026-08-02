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
      "Opening block identifying the issuing government, department, document type, and official GR number.",
    detectionHints: [
      "महाराष्ट्र शासन or GOVERNMENT OF MAHARASHTRA",
      "Document type: शासन निर्णय, शासन परिपत्रक, शासन पत्र, etc.",
      "Official number after क्रमांक / क्र. / No.",
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
      "A clear subject describing the policy matter — typically labelled विषय: or as title lines above the government header.",
    detectionHints: [
      "विषय: followed by the policy subject text",
      "Or title lines appearing before महाराष्ट्र शासन",
    ],
    severityMissing: "high",
    severityMisordered: "high",
  },
  {
    order: 3,
    id: "references_section",
    label: "References (वाचा) section",
    labelMr: "वाचा / संदर्भ",
    required: false,
    description:
      "Lists prior GRs, circulars, or files being read or relied upon. Optional but expected in formal resolutions.",
    detectionHints: [
      "Section headed वाचा, बाचा, संदर्भ, or Reference",
      "Numbered reference items (१., 2., etc.) with dates where applicable",
    ],
    severityMissing: "low",
    severityMisordered: "low",
  },
  {
    order: 4,
    id: "operative_section",
    label: "Operative / decision paragraph(s)",
    labelMr: "शासन निर्णय / ऑपरेटिव्ह परिच्छेद",
    required: true,
    description:
      "The binding decision text — approvals, sanctions, directives, or numbered operative clauses.",
    detectionHints: [
      "शासन निर्णय : (not the header क्रमांक line)",
      "यान्वये … मंजूर operative formula",
      "Numbered clauses: कलम / Section / Clause",
    ],
    severityMissing: "high",
    severityMisordered: "medium",
  },
  {
    order: 5,
    id: "signatory_block",
    label: "Signatory block",
    labelMr: "स्वाक्षरी खंड",
    required: true,
    description:
      "Closing signature with designation and department — a GR without this is usually not considered valid.",
    detectionHints: [
      "(सचिव) or Secretary designation near document end",
      "Department name below the signatory line",
    ],
    severityMissing: "high",
    severityMisordered: "medium",
  },
];

export const GR_TEMPLATE_SCORING_NOTE =
  "Template accuracy scores required sections in this order: full credit when present and correctly ordered, half credit when present but misordered, zero when missing.";
