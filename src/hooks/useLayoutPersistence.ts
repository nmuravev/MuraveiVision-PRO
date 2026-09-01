// src/hooks/useLayoutPersistence.ts
import { useState, useCallback } from 'react'

const LAYOUT_STORAGE_KEY = 'muraveivision-layout'

interface LayoutState {
  layout: Record<string, number>
  isDefault: boolean
}

export function useLayoutPersistence(defaultLayout: Record<string, number>) {
  const [layoutState, setLayoutState] = useState<LayoutState>(() => {
    try {
      const saved = localStorage.getItem(LAYOUT_STORAGE_KEY)
      if (saved) {
        return { layout: JSON.parse(saved) as Record<string, number>, isDefault: false }
      }
    } catch (e) {
      console.warn('Failed to load layout from localStorage:', e)
    }
    return { layout: defaultLayout, isDefault: true }
  })

  const saveLayout = useCallback((newLayout: Record<string, number>) => {
    try {
      localStorage.setItem(LAYOUT_STORAGE_KEY, JSON.stringify(newLayout))
      setLayoutState({ layout: newLayout, isDefault: false })
    } catch (e) {
      console.warn('Failed to save layout:', e)
    }
  }, [])

  const resetLayout = useCallback(() => {
    try {
      localStorage.removeItem(LAYOUT_STORAGE_KEY)
      setLayoutState({ layout: defaultLayout, isDefault: true })
    } catch (e) {
      console.warn('Failed to reset layout:', e)
    }
  }, [defaultLayout])

  return {
    layout: layoutState.layout,
    isDefault: layoutState.isDefault,
    saveLayout,
    resetLayout,
  }
}
