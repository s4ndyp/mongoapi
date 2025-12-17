tailwind.config = {
    darkMode: 'class',
    theme: {
        extend: {
            colors: {
                primary: 'rgb(var(--color-primary) / <alpha-value>)', 
                secondary: '#10b981',
                dark: '#0f172a', 
                dark_paper: '#1e293b', 
                accent: '#8b5cf6'
            },
            fontFamily: {
                sans: ['Inter', 'sans-serif'],
            }
        }
    }
}
