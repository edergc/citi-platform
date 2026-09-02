import loginBuilding from '@/assets/login-building.jpg'

export function InstitutionalHeaderBackdrop() {
  return (
    <>
      <div
        className="absolute inset-0 bg-cover"
        style={{ backgroundImage: `url(${loginBuilding})`, backgroundPosition: '50% 22%' }}
      />
      <div className="absolute inset-0 bg-red-950/90" />
      <div
        className="pointer-events-none absolute inset-0 opacity-20"
        style={{ backgroundImage: 'radial-gradient(circle at 15% 50%, rgba(251,191,36,0.3), transparent 50%)' }}
      />
    </>
  )
}
