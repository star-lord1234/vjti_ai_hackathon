import React, { useState, useEffect, useRef } from "react";
import {
  Palette,
  Save,
  Eye,
  RefreshCw,
  Upload,
  RotateCcw,
  CheckCircle2,
  AlertTriangle,
  FileText,
  Type,
  Layers,
} from "lucide-react";
import {
  PdfTemplate,
  getTemplate,
  updateTemplate,
  getTemplatePdfPreviewUrl,
} from "../../lib/api";

const FONT_OPTIONS = [
  "Noto Sans",
  "Noto Serif",
  "Lato",
  "Open Sans",
  "Roboto",
  "Merriweather",
  "Source Sans Pro",
];

const DEFAULT_TEMPLATE: Partial<PdfTemplate> = {
  department: "महाराष्ट्र शासन",
  header_line: "उच्च व तंत्र शिक्षण विभाग",
  footer_text: "महाराष्ट्राचे राज्यपाल यांच्या आदेशानुसार व नावाने",
  font_family: "Noto Sans",
  margins_pt: 72,
};

export const PdfTemplateEditor: React.FC = () => {
  const [template, setTemplate] = useState<Partial<PdfTemplate>>(DEFAULT_TEMPLATE);
  const [original, setOriginal] = useState<Partial<PdfTemplate>>(DEFAULT_TEMPLATE);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saveStatus, setSaveStatus] = useState<"idle" | "success" | "error">("idle");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [previewKey, setPreviewKey] = useState(0);
  const [previewLoading, setPreviewLoading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const isDirty = JSON.stringify(template) !== JSON.stringify(original);

  useEffect(() => {
    loadTemplate();
  }, []);

  const loadTemplate = async () => {
    setLoading(true);
    try {
      const tmpl = await getTemplate();
      setTemplate(tmpl);
      setOriginal(tmpl);
    } catch (err: any) {
      setErrorMsg("Failed to load template: " + (err?.message || "Unknown error"));
    } finally {
      setLoading(false);
    }
  };

  const handleChange = (field: keyof PdfTemplate, value: string | number) => {
    setTemplate((prev) => ({ ...prev, [field]: value }));
    setSaveStatus("idle");
  };

  const handleLogoUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const b64 = (reader.result as string).split(",")[1];
      setTemplate((prev) => ({ ...prev, logo_base64: b64 }));
      setSaveStatus("idle");
    };
    reader.readAsDataURL(file);
  };

  const handleRemoveLogo = () => {
    setTemplate((prev) => ({ ...prev, logo_base64: undefined }));
    setSaveStatus("idle");
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleSave = async () => {
    setSaving(true);
    setSaveStatus("idle");
    try {
      const { id, updated_at, ...fields } = template as any;
      const saved = await updateTemplate(fields);
      setOriginal(saved);
      setTemplate(saved);
      setSaveStatus("success");
    } catch (err: any) {
      setSaveStatus("error");
      setErrorMsg(err?.message || "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    setTemplate(original);
    setSaveStatus("idle");
  };

  const handlePreview = () => {
    setPreviewLoading(true);
    setPreviewKey((k) => k + 1);
    window.open(getTemplatePdfPreviewUrl(), "_blank");
    setTimeout(() => setPreviewLoading(false), 1000);
  };

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center bg-[#0d1117]">
        <div className="text-center">
          <div className="w-10 h-10 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <p className="text-sm font-medium text-gray-400">Loading PDF template...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col bg-[#0d1117] min-h-0 font-sans text-white overflow-hidden">
      {/* Header */}
      <div className="bg-[#161b22] border-b border-white/10 px-8 py-5 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-indigo-500/20 border border-indigo-400/30 flex items-center justify-center">
            <Palette size={18} className="text-indigo-400" />
          </div>
          <div>
            <h1 className="text-base font-bold text-white">PDF Letterhead Template</h1>
            <p className="text-xs text-gray-400 mt-0.5">Configure the GR export layout and branding</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {isDirty && (
            <button
              onClick={handleReset}
              className="px-3 py-2 text-xs font-medium text-gray-400 hover:text-white border border-white/10 rounded-lg flex items-center gap-1.5 transition-colors"
            >
              <RotateCcw size={13} />
              Discard
            </button>
          )}
          <button
            onClick={handlePreview}
            disabled={previewLoading}
            className="px-3 py-2 bg-indigo-600/20 hover:bg-indigo-600/30 text-indigo-300 border border-indigo-400/30 text-xs font-semibold rounded-lg flex items-center gap-1.5 transition-colors"
          >
            <Eye size={13} />
            Preview PDF
          </button>
          <button
            onClick={handleSave}
            disabled={saving || !isDirty}
            className={`px-4 py-2 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-all ${
              isDirty
                ? "bg-indigo-600 hover:bg-indigo-700 text-white shadow-lg shadow-indigo-500/20"
                : "bg-white/5 text-gray-500 cursor-not-allowed"
            }`}
          >
            <Save size={13} />
            {saving ? "Saving..." : "Save Template"}
          </button>
        </div>
      </div>

      {/* Status Banner */}
      {saveStatus === "success" && (
        <div className="mx-8 mt-4 px-4 py-2.5 bg-emerald-500/10 border border-emerald-500/30 rounded-xl flex items-center gap-2 text-xs text-emerald-400 font-medium">
          <CheckCircle2 size={14} />
          Template saved successfully. All future PDF exports will use this layout.
        </div>
      )}
      {saveStatus === "error" && (
        <div className="mx-8 mt-4 px-4 py-2.5 bg-red-500/10 border border-red-500/30 rounded-xl flex items-center gap-2 text-xs text-red-400 font-medium">
          <AlertTriangle size={14} />
          {errorMsg}
        </div>
      )}

      {/* Body */}
      <div className="flex-1 overflow-y-auto p-8">
        <div className="max-w-3xl mx-auto space-y-6">

          {/* Section: Letterhead Identity */}
          <TemplateSection icon={<Layers size={15} />} title="Letterhead Identity">
            <TemplateField
              label="Department Name (Marathi)"
              hint="Displayed as the large primary heading"
              value={template.department ?? ""}
              onChange={(v) => handleChange("department", v)}
            />
            <TemplateField
              label="Sub-Department / Header Line"
              hint="Displayed below the main department name"
              value={template.header_line ?? ""}
              onChange={(v) => handleChange("header_line", v)}
            />
          </TemplateSection>

          {/* Section: Footer */}
          <TemplateSection icon={<FileText size={15} />} title="Footer Text">
            <TemplateField
              label="Footer Signing Authority Line"
              hint="Appears at the bottom of each page"
              value={template.footer_text ?? ""}
              onChange={(v) => handleChange("footer_text", v)}
            />
          </TemplateSection>

          {/* Section: Typography & Layout */}
          <TemplateSection icon={<Type size={15} />} title="Typography & Layout">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-gray-300 mb-2">Font Family</label>
                <select
                  value={template.font_family ?? "Noto Sans"}
                  onChange={(e) => handleChange("font_family", e.target.value)}
                  className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                >
                  {FONT_OPTIONS.map((f) => (
                    <option key={f} value={f} className="bg-gray-900">
                      {f}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs font-semibold text-gray-300 mb-2">
                  Page Margins (pt) — current: {template.margins_pt ?? 72}pt
                </label>
                <input
                  type="range"
                  min={36}
                  max={108}
                  step={9}
                  value={template.margins_pt ?? 72}
                  onChange={(e) => handleChange("margins_pt", parseInt(e.target.value))}
                  className="w-full mt-2 accent-indigo-500"
                />
                <div className="flex justify-between text-[10px] text-gray-500 mt-1">
                  <span>Narrow (36pt)</span>
                  <span>Wide (108pt)</span>
                </div>
              </div>
            </div>
          </TemplateSection>

          {/* Section: Logo */}
          <TemplateSection icon={<Upload size={15} />} title="Letterhead Logo">
            <div className="flex items-start gap-6">
              <div className="flex-1">
                <p className="text-xs text-gray-400 mb-3">
                  Upload a PNG or SVG logo (e.g. Maharashtra state seal) to appear above the department name.
                  Leave blank to use no logo.
                </p>
                <div className="flex gap-3">
                  <label className="px-4 py-2 bg-white/5 border border-white/15 hover:border-indigo-400/50 rounded-lg text-xs text-gray-300 font-medium cursor-pointer transition-colors flex items-center gap-2">
                    <Upload size={13} />
                    Upload Logo
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept="image/png,image/svg+xml,image/jpeg"
                      onChange={handleLogoUpload}
                      className="hidden"
                    />
                  </label>
                  {template.logo_base64 && (
                    <button
                      onClick={handleRemoveLogo}
                      className="px-3 py-2 text-xs text-red-400 hover:text-red-300 border border-red-400/20 rounded-lg transition-colors"
                    >
                      Remove
                    </button>
                  )}
                </div>
              </div>
              {template.logo_base64 && (
                <div className="w-20 h-20 bg-white rounded-lg flex items-center justify-center overflow-hidden border border-white/20 shrink-0">
                  <img
                    src={`data:image/png;base64,${template.logo_base64}`}
                    alt="Logo Preview"
                    className="max-w-full max-h-full object-contain"
                  />
                </div>
              )}
            </div>
          </TemplateSection>

          {/* Live Preview Card */}
          <div className="bg-[#161b22] border border-white/10 rounded-2xl p-6">
            <div className="text-xs font-semibold text-gray-400 mb-4 flex items-center gap-2">
              <Eye size={13} />
              Layout Preview
            </div>
            <div className="bg-white rounded-xl p-6 text-gray-900 font-serif shadow-inner text-center">
              <div className="border-b-2 border-double border-[#1a3a6e] pb-3 mb-4">
                <div className="text-xl font-bold text-[#1a3a6e]">{template.department || "—"}</div>
                <div className="text-sm text-gray-600 mt-1">{template.header_line || "—"}</div>
              </div>
              <div className="text-left text-xs text-gray-400 italic mb-4">
                [GR Number] · [Date] · [Subject line]
              </div>
              <div className="text-left text-xs text-gray-600 leading-relaxed">
                शासन निर्णयाचा मुख्य मजकूर येथे असेल...
              </div>
              <div className="border-t border-gray-200 mt-4 pt-3 flex justify-between text-[10px] text-gray-400">
                <span>{template.footer_text || "—"}</span>
                <span>1 / 1</span>
              </div>
            </div>
          </div>

        </div>
      </div>
    </div>
  );
};

// ── Sub-components ─────────────────────────────────────────────────────────────

const TemplateSection: React.FC<{
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
}> = ({ icon, title, children }) => (
  <div className="bg-[#161b22] border border-white/10 rounded-2xl p-6">
    <div className="flex items-center gap-2 text-xs font-bold text-indigo-400 mb-4">
      {icon}
      {title}
    </div>
    <div className="space-y-4">{children}</div>
  </div>
);

const TemplateField: React.FC<{
  label: string;
  hint: string;
  value: string;
  onChange: (v: string) => void;
}> = ({ label, hint, value, onChange }) => (
  <div>
    <label className="block text-xs font-semibold text-gray-300 mb-1">{label}</label>
    <p className="text-[11px] text-gray-500 mb-2">{hint}</p>
    <input
      type="text"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2.5 text-sm text-white placeholder-gray-600 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-all"
    />
  </div>
);
