interface Window {
  desktop?: {
    version: () => Promise<string>;
    openExternal: (url: string) => Promise<unknown>;
    savePdf: (html: string, filename: string) => Promise<{ filePath?: string; canceled?: boolean }>;
    minimize: () => void;
    toggleMaximize: () => void;
    close: () => void;
  };
}
