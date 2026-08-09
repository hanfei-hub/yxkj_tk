interface Window {
  desktop?: {
    version: () => Promise<string>;
    openExternal: (url: string) => Promise<unknown>;
    minimize: () => void;
    toggleMaximize: () => void;
    close: () => void;
  };
}
