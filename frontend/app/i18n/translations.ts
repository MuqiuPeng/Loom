export type Language = 'zh' | 'en'

export const translations = {
  zh: {
    // Header
    appTitle: 'Profile Builder',
    appSubtitle: '通过对话挖掘你的经历亮点',
    newChat: '新对话',
    myResume: '我的简历',
    realtimePreview: '实时更新的内容预览',

    // Quick actions
    welcomeTitle: '开始整理你的简历',
    welcomeDescription: '告诉我你的工作经历或项目，我会帮你挖掘亮点，整理成专业的简历内容。',
    addWorkExperience: '添加工作经历',
    addProject: '添加项目',
    startFromScratch: '从头开始',
    addWorkExperiencePrompt: '我想添加一段工作经历',
    addProjectPrompt: '我想添加一个项目经历',
    startFromScratchPrompt: '你好，我想整理一下我的简历',

    // Input
    inputPlaceholder: '输入你的经历或回答问题... (Shift+Enter 换行)',

    // Loading states
    organizing: '正在整理你的经历...',
    thinking: '正在思考...',

    // Profile panel
    noContent: '还没有内容',
    noContentHint: '通过左侧对话添加你的经历，\n整理后的内容会显示在这里',
    skills: '技能',
    workExperience: '工作经历',
    projects: '项目',
    education: '教育背景',
    present: '至今',
    saved: '已保存',
    highlights: '条亮点',

    // Skill levels
    expert: '精通',
    proficient: '熟练',
    familiar: '了解',

    // Language
    language: '语言',
    chinese: '中文',
    english: 'English',
  },
  en: {
    // Header
    appTitle: 'Profile Builder',
    appSubtitle: 'Discover highlights in your experiences through conversation',
    newChat: 'New Chat',
    myResume: 'My Resume',
    realtimePreview: 'Real-time content preview',

    // Quick actions
    welcomeTitle: 'Start Building Your Resume',
    welcomeDescription: 'Tell me about your work experience or projects, and I\'ll help you discover highlights and organize them professionally.',
    addWorkExperience: 'Add Work Experience',
    addProject: 'Add Project',
    startFromScratch: 'Start Fresh',
    addWorkExperiencePrompt: 'I want to add a work experience',
    addProjectPrompt: 'I want to add a project',
    startFromScratchPrompt: 'Hi, I want to organize my resume',

    // Input
    inputPlaceholder: 'Share your experience or answer questions... (Shift+Enter for new line)',

    // Loading states
    organizing: 'Organizing your experience...',
    thinking: 'Thinking...',

    // Profile panel
    noContent: 'No content yet',
    noContentHint: 'Add your experiences through the chat on the left,\nand organized content will appear here',
    skills: 'Skills',
    workExperience: 'Work Experience',
    projects: 'Projects',
    education: 'Education',
    present: 'Present',
    saved: 'Saved',
    highlights: 'highlights',

    // Skill levels
    expert: 'Expert',
    proficient: 'Proficient',
    familiar: 'Familiar',

    // Language
    language: 'Language',
    chinese: '中文',
    english: 'English',
  },
} as const

export type TranslationKey = keyof typeof translations.zh

export function t(key: TranslationKey, lang: Language): string {
  return translations[lang][key]
}
