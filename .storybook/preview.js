import "../src/styles.css";

const preview = {
  parameters: {
    actions: { argTypesRegex: "^on[A-Z].*" },
    a11y: {
      test: "todo",
    },
    backgrounds: {
      default: "Canvas",
      values: [
        { name: "Canvas", value: "#f6f8f5" },
        { name: "Surface", value: "#ffffff" },
        { name: "Ink", value: "#101614" },
      ],
    },
    controls: {
      matchers: {
        color: /(background|color)$/i,
        date: /Date$/i,
      },
    },
    layout: "fullscreen",
  },
};

export default preview;
