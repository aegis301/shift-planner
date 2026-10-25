module.exports = {
  root: true,
  extends: ["expo"],
  ignorePatterns: ["node_modules/", ".expo/", "dist/"],
  rules: {
    "no-restricted-imports": [
      "error",
      {
        paths: [
          { name: "next", message: "The member app has no web framework code." },
          { name: "react-dom", message: "The member app renders React Native, not the DOM." }
        ]
      }
    ]
  }
};
