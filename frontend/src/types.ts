export type StudioId = 'manuscript' | 'charts' | 'diagrams' | 'patcher' | 'citations';

export interface ProviderConfig {
  id: string;
  name: string;
  region: 'domestic' | 'international' | 'local' | 'custom';
  protocol: 'openai' | 'anthropic' | 'anthropic_relay';
  base_url: string;
  has_key: boolean;
  api_key_masked: string;
  models: string[];
  default_model: string;
}

export interface SettingsPayload {
  providers: ProviderConfig[];
  routing: {
    writing: { provider_id: string; model: string };
    vision: { provider_id: string; model: string };
    image: { provider_id: string; model: string };
  };
  search?: {
    provider: 'builtin_free' | 'bocha' | 'tavily' | 'serper';
    has_key: boolean;
    api_key_masked: string;
  };
  preferences: {
    default_venue: string;
    cjk_latin_space: boolean;
    author_name: string;
    theme: 'paper' | 'ink';
    lang?: 'zh' | 'en';
    style_strength?: 'natural' | 'balanced' | 'venue_strict';
    first_mention_en?: boolean;
  };
}

export interface EditCard {
  id: string;
  original: string;
  revised: string;
  tag: string;
  reason: string;
  status: 'pending' | 'accepted' | 'rejected';
}

export interface OutlineItem {
  kind: 'section' | 'equation';
  level: number;
  title: string;
  line: number;
}

export interface FormulaBlock {
  id: string;
  kind: 'heading' | 'paragraph' | 'equation';
  text?: string;
  display?: boolean;
  number?: number;
  label?: string;
  latex?: string;
}

export interface FormulaRecommendation {
  id: string;
  after_block_index: number;
  recommended_mode: 'display' | 'inline';
  trigger: string;
  rationale: string;
  suggested_latex: string;
  suggested_label: string;
  suggested_where: string;
}

export interface DiagramBlueprint {
  title: string;
  venue_theme: string;
  layout_mode?: string;
  custom_colors?: Record<string, string>;
  width: number;
  height: number;
  font_size: number;
  corner_radius: number;
  groups: Array<{ id: string; label: string; x: number; y: number; w: number; h: number; tone: string }>;
  nodes: Array<{
    id: string;
    label: string;
    sublabel: string;
    x: number;
    y: number;
    w: number;
    h: number;
    tone: string;
    icon: string;
    ai_image_b64?: string;
  }>;
  edges: Array<{ from: string; to: string; label: string; dashed: boolean }>;
}

export interface CorpusPack {
  id: string;
  name: string;
  domain: string;
  venue: string;
  language: string;
  readonly: boolean;
  enabled: boolean;
  weight: number;
  paper_count: number;
  sentence_count: number;
  has_vectors: boolean;
  size_mb: number;
  updated_at: string;
  papers: Array<{
    id: string;
    title: string;
    venue: string;
    year: number;
    group: string;
    sentences: number;
    added_at: string;
  }>;
  style_profile?: {
    sentence_count: number;
    avg_sentence_len: number;
    section_distribution: Record<string, number>;
    top_we_verbs: Array<{ verb: string; count: number }>;
    top_openers: Array<{ opener: string; count: number }>;
    top_transitions: Array<{ transition: string; count: number }>;
    cn_overused_logodds: Array<{ phrase: string; z: number; cn: number; native: number }>;
    distilled_at: string;
  } | null;
}
