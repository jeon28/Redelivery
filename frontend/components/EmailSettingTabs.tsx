'use client'
import { useState } from 'react'
import RecipientRulesTab from './RecipientRulesTab'
import EmailTemplateTab from './EmailTemplateTab'

export default function EmailSettingTabs({ office }: { office: string }) {
  const [tab, setTab] = useState<'rules' | 'template'>('rules')

  return (
    <>
      <div className="flex gap-2 mb-4">
        <button
          type="button"
          onClick={() => setTab('rules')}
          className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
            tab === 'rules'
              ? 'bg-slate-800 text-white'
              : 'bg-white text-gray-700 border border-gray-300 hover:bg-gray-50'
          }`}
        >
          Recipient Rules
        </button>
        <button
          type="button"
          onClick={() => setTab('template')}
          className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
            tab === 'template'
              ? 'bg-slate-800 text-white'
              : 'bg-white text-gray-700 border border-gray-300 hover:bg-gray-50'
          }`}
        >
          Email Template
        </button>
      </div>

      {tab === 'rules' ? (
        <RecipientRulesTab office={office} />
      ) : (
        <EmailTemplateTab office={office} />
      )}
    </>
  )
}
