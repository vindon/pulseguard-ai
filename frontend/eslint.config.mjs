import nextConfig from "eslint-config-next";

const eslintConfig = [
  ...nextConfig,
  {
    ignores: ["e2e/**", "playwright-report/**", "test-results/**", ".next/**"],
  },
];

export default eslintConfig;
