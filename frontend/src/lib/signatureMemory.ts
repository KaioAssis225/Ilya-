const profileSignatures = new Map<string, string>()

export function getProfileSignature(userId: string): string | null {
  return profileSignatures.get(userId) ?? null
}

export function setProfileSignature(userId: string, signature: string): void {
  profileSignatures.set(userId, signature)
}

export function clearSignatureMemory(): void {
  profileSignatures.clear()
}

export function removeLegacySignatureStorage(): void {
  for (const key of Object.keys(localStorage)) {
    if (key.startsWith('profile_signature_') || key.startsWith('signature_')) {
      localStorage.removeItem(key)
    }
  }
}
