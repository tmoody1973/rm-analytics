const API = import.meta.env.VITE_API_URL || 'https://rm-data-loader.fly.dev'
export async function fetchDashboard() {
  const r = await fetch(`${API}/api/dashboard`)
  if (!r.ok) throw new Error(`Dashboard API returned ${r.status}`)
  return r.json()
}
