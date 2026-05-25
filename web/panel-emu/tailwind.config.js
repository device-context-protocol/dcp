/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{vue,js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        // Match the firmware role colors so the emulator stays 1:1 with hw.
        role: {
          user:   "rgb(20, 150, 200)",   // cyan
          llm:    "rgb(220, 160, 20)",   // amber
          dcp_ok: "rgb(30, 170, 60)",    // green
          dcp_err:"rgb(210, 40, 40)",    // red
          dcp_req:"rgb(110, 110, 130)",  // gray
          plain:  "rgb(0, 0, 0)",        // black
        },
        panel: {
          bg:     "rgb(255, 255, 255)",    // white background
          header: "rgb(110, 110, 130)",    // device id strip
          status: "rgb(40, 50, 70)",       // status bar slate
          sep:    "rgb(190, 195, 210)",
          footer: "rgb(150, 150, 165)",
        },
      },
      fontFamily: {
        // T-Panel uses lv_font_montserrat_14 — a clean sans
        panel: ["Inter", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};
