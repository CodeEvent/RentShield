import { CommonModule } from '@angular/common'
import { Component, computed, inject, OnInit, signal } from '@angular/core'
import { NgxBootstrapIconsModule } from 'ngx-bootstrap-icons'
import { ActivatedRoute, Router } from '@angular/router'
import { Notice, RdscReadiness, RentshieldApiService } from '../services/rentshield-api.service'
import { NoticeWindowComponent } from './notice-window/notice-window.component'
import {
  Inspection,
  MaintenanceItem,
  Message,
  PropertyWorkspaceService,
  Reminder,
} from '../services/property-workspace.service'

interface NavItem {
  k: string
  l: string
}

/** A property derived from the real notices that reference it. The address is
 *  the record; its details come from the notices themselves (no separate
 *  property endpoint exists yet). */
interface Property {
  key: string
  id: string
  address: string
  type: string
  community: string
  plot: string
  ejari: string
  status: string
  ownerVerified: boolean
  owner: string
  tenant: string
  annualRent: string
  contractStart: string
  contractEnds: string
  ejariExpiry: string | null
  noticeWindowDays: number
  openNotices: number
  notices: Notice[]
}

/**
 * The property record is the hub of the owner's workspace: the address IS
 * the record, and every management concern (tenancy, notices, documents,
 * compliance, payments, disputes...) is a tab around it. The Notices tab is
 * wired to the real notices API (RentshieldApiService.listNotices) and scoped
 * to this property by unit/building; other tabs use mock data or a friendly
 * empty state until their own endpoints land.
 */
@Component({
  selector: 'app-property-record',
  standalone: true,
  imports: [CommonModule, NgxBootstrapIconsModule, NoticeWindowComponent],
  templateUrl: './property-record.component.html',
  styleUrl: './property-record.component.scss',
})
export class PropertyRecordComponent implements OnInit {
  private api = inject(RentshieldApiService)
  private router = inject(Router)
  private route = inject(ActivatedRoute)
  private workspace = inject(PropertyWorkspaceService)

  readonly sections: NavItem[] = [
    { k: 'overview', l: 'Overview' },
    { k: 'tenancy', l: 'Tenancy' },
    { k: 'tenant', l: 'Tenant' },
    { k: 'notices', l: 'Notices' },
    { k: 'documents', l: 'Documents' },
    { k: 'verification', l: 'Verification' },
    { k: 'payments', l: 'Payments' },
    { k: 'disputes', l: 'Disputes' },
    { k: 'timeline', l: 'Timeline' },
    { k: 'compliance', l: 'Compliance' },
    { k: 'tasks', l: 'Tasks' },
    { k: 'notes', l: 'Notes' },
    { k: 'reminders', l: 'Reminders' },
    { k: 'inspections', l: 'Inspections' },
    { k: 'maintenance', l: 'Maintenance' },
    { k: 'messages', l: 'Messages' },
  ]

  readonly subNav: Record<string, NavItem[]> = {
    overview: [
      { k: 'summary', l: 'Summary' },
      { k: 'people', l: 'Key people' },
      { k: 'location', l: 'Location & Ejari' },
    ],
    tenancy: [
      { k: 'current', l: 'Current contract' },
      { k: 'history', l: 'Contract history' },
      { k: 'rent', l: 'Rent schedule' },
    ],
    tenant: [
      { k: 'current', l: 'Current tenant' },
      { k: 'past', l: 'Past tenants' },
    ],
    notices: [
      { k: 'all', l: 'All notices' },
      { k: 'drafts', l: 'Drafts' },
      { k: 'served', l: 'Served' },
      { k: 'disputed', l: 'Disputed' },
    ],
    documents: [
      { k: 'contract', l: 'Tenancy contract' },
      { k: 'ejari', l: 'Ejari certificate' },
      { k: 'notices', l: 'Notices' },
    ],
    verification: [
      { k: 'owner', l: 'Owner verification' },
      { k: 'authority', l: 'Authority to act' },
    ],
    payments: [
      { k: 'invoices', l: 'Invoices' },
      { k: 'receipts', l: 'Receipts' },
    ],
    disputes: [
      { k: 'cases', l: 'Cases' },
      { k: 'hearings', l: 'Hearings' },
    ],
    timeline: [{ k: 'activity', l: 'Activity' }],
    compliance: [
      { k: 'checklist', l: 'Article 25 checklist' },
      { k: 'deadlines', l: 'Deadlines' },
    ],
    tasks: [
      { k: 'open', l: 'Open' },
      { k: 'done', l: 'Done' },
    ],
    notes: [{ k: 'all', l: 'All notes' }],
    reminders: [{ k: 'all', l: 'All reminders' }],
    inspections: [{ k: 'all', l: 'All inspections' }],
    maintenance: [{ k: 'all', l: 'All' }],
    messages: [{ k: 'inbox', l: 'Inbox' }],
  }

  readonly section = signal('overview')
  readonly sub = signal('summary')
  readonly subs = computed<NavItem[]>(() => this.subNav[this.section()] ?? [])

  // ---- real notices (RentshieldApiService) ----
  readonly allNotices = signal<Notice[]>([])
  readonly noticesLoading = signal(true)

  // Group the live notices into properties: the physical address (building +
  // unit/plot) is the record. Each property's details are read off its own
  // notices — there is no separate property endpoint yet.
  readonly properties = computed<Property[]>(() => {
    const groups = new Map<string, Notice[]>()
    for (const n of this.allNotices()) {
      const unit = n.unit_no || n.plot_number || ''
      const key = `${n.building_name || 'Unknown'}|${unit}`
      const arr = groups.get(key) ?? []
      arr.push(n)
      groups.set(key, arr)
    }
    const out: Property[] = []
    for (const [key, notices] of groups) {
      // newest notice drives the "current" owner/tenant view
      const latest = [...notices].sort((a, b) => (b.notice_date || '').localeCompare(a.notice_date || ''))[0]
      const unit = latest.unit_no || ''
      const plot = latest.plot_number || ''
      const building = latest.building_name || 'Unknown building'
      const addr = unit ? `${building}, Unit ${unit}` : plot ? `${building}, Plot ${plot}` : building
      const open = notices.filter((n) => !n.served_date).length
      out.push({
        key,
        id: unit || plot || key,
        address: addr,
        type: latest.property_type || '—',
        community: building,
        plot: plot || '—',
        ejari: latest.ejari_number || '—',
        status: notices.some((n) => n.served_date) ? 'Notice served' : 'Occupied',
        ownerVerified: false,
        owner: latest.landlord_name || '—',
        tenant: latest.tenant_name || '—',
        annualRent: '—',
        contractStart: '—',
        contractEnds: latest.contract_expiry
          ? new Date(latest.contract_expiry).toLocaleDateString('en-GB', {
              day: '2-digit',
              month: 'short',
              year: 'numeric',
            })
          : '—',
        // Drives the Notice Window widget (365-day statutory buffer). Null
        // when the notice carries no registered contract-expiry date, which
        // hides the widget rather than inventing a date.
        ejariExpiry: latest.contract_expiry,
        noticeWindowDays: 0,
        openNotices: open,
        notices,
      })
    }
    return out.sort((a, b) => a.address.localeCompare(b.address))
  })

  // Which property is in focus. Defaults to the first once notices load.
  readonly selectedKey = signal<string | null>(null)
  readonly property = computed<Property | null>(() => {
    const all = this.properties()
    if (all.length === 0) return null
    return all.find((p) => p.key === this.selectedKey()) ?? all[0]
  })

  readonly propertyNotices = computed<Notice[]>(() => this.property()?.notices ?? [])

  // Real reminders derived from this property's live notices.
  readonly reminders = computed<Reminder[]>(() => {
    const out: Reminder[] = []
    for (const n of this.propertyNotices()) {
      if (!n.served_date) {
        out.push({ id: n.id, title: `Serve notice #${n.id}`, due: 'pending', kind: 'notice', urgent: true })
      }
      if (n.add_real_notarization && n.notary_status && n.notary_status !== 'completed') {
        out.push({ id: 1000 + n.id, title: `Notice #${n.id} awaiting Notary`, due: 'in review', kind: 'notice', urgent: false })
      }
    }
    return out
  })
  readonly inspections = signal<Inspection[]>([])
  readonly maintenance = signal<MaintenanceItem[]>([])
  readonly messages = signal<Message[]>([])

  // ---- RDSC factual compliance audit matrix (hard gate) ----
  // The notice this property's dispute packet would be compiled from: the
  // first served notice, else the first notice on the property.
  readonly rdscNotice = computed<Notice | null>(() => {
    const notices = this.propertyNotices()
    return notices.find((n) => !!n.served_date) ?? notices[0] ?? null
  })
  readonly rdscReadiness = signal<RdscReadiness | null>(null)
  readonly rdscLoading = signal(false)
  readonly rdscCompiling = signal(false)
  readonly rdscMessage = signal('')

  readonly checklist = [
    { ok: true, text: 'Reason matched to the correct period (12-month)' },
    { ok: true, text: 'Notice in English and Arabic' },
    { ok: true, text: 'Article 25(2) cited' },
    { ok: false, text: 'Served via a recognised channel (not yet)' },
  ]

  readonly activity = [
    { when: 'Today 10:04', text: 'Notice generated' },
    { when: '09 Oct', text: 'Owner identity verified' },
    { when: '16 Sep 2024', text: 'Tenancy contract started' },
  ]

  ngOnInit(): void {
    this.api.listNotices().subscribe({
      next: (notices) => {
        this.allNotices.set(notices)
        this.noticesLoading.set(false)
        // Focus the first property (or the one named by the :id route param,
        // matched against a notice id) once real data is in.
        const routeId = this.route.snapshot.paramMap.get('id')
        const match = routeId
          ? this.properties().find((p) => p.notices.some((n) => String(n.id) === routeId))
          : undefined
        this.selectedKey.set((match ?? this.properties()[0])?.key ?? null)
        this.loadWorkspaceExtras()
      },
      error: () => this.noticesLoading.set(false),
    })
  }

  /** Mock inspections/maintenance/messages, scoped to the focused property. */
  private loadWorkspaceExtras(): void {
    const id = this.property()?.id ?? 'none'
    this.workspace.getInspections(id).subscribe((r) => this.inspections.set(r))
    this.workspace.getMaintenance(id).subscribe((r) => this.maintenance.set(r))
    this.workspace.getMessages(id).subscribe((r) => this.messages.set(r))
  }

  /** Switch the focused property (header dropdown). */
  selectProperty(key: string): void {
    this.selectedKey.set(key)
    this.loadWorkspaceExtras()
    if (this.section() === 'disputes') {
      this.loadRdscReadiness()
    }
  }

  noticeStatus(n: Notice): { label: string; cls: string } {
    if (n.notary_status === 'completed') {
      return { label: 'Notarized', cls: 'ok' }
    }
    if (n.add_real_notarization && n.notary_status) {
      return { label: 'Awaiting Notary', cls: 'warn' }
    }
    if (n.esign_status === 'completed') {
      return { label: 'E-signed', cls: 'ok' }
    }
    if (n.add_notarization) {
      return { label: 'E-signature due', cls: 'warn' }
    }
    if (n.served_date) {
      return { label: 'Served', cls: 'ok' }
    }
    return { label: 'Generated', cls: 'slate' }
  }

  /** Open the notice form prefilled with this property's details. */
  newNotice(): void {
    const p = this.property()
    if (!p) {
      this.router.navigate(['/notice/new'])
      return
    }
    this.router.navigate(['/notice/new'], {
      queryParams: {
        landlord_name: p.owner,
        tenant_name: p.tenant,
        property_type: p.type,
        unit_no: p.id,
        building_name: p.community,
        plot_number: p.plot === '—' ? '' : p.plot,
        ejari_number: p.ejari === '—' ? '' : p.ejari,
      },
    })
  }

  /** Fetch the deterministic readiness matrix for the dispute's notice. */
  loadRdscReadiness(): void {
    const notice = this.rdscNotice()
    this.rdscMessage.set('')
    if (!notice) {
      this.rdscReadiness.set(null)
      return
    }
    this.rdscLoading.set(true)
    this.api.getRdscReadiness(notice.id).subscribe({
      next: (r) => {
        this.rdscReadiness.set(r)
        this.rdscLoading.set(false)
      },
      error: () => {
        this.rdscReadiness.set(null)
        this.rdscLoading.set(false)
        this.rdscMessage.set('Could not load the compliance matrix. Please try again.')
      },
    })
  }

  /** Compile the RDSC packet -- only when the gate is open. The server
   *  re-checks the same gate, so this guard is UX, not the security boundary. */
  compileRdscPacket(): void {
    const notice = this.rdscNotice()
    const readiness = this.rdscReadiness()
    if (!notice || !readiness?.can_compile || this.rdscCompiling()) {
      return
    }
    this.rdscCompiling.set(true)
    this.rdscMessage.set('')
    this.api.generateRdscPacket(notice.id).subscribe({
      next: () => {
        this.rdscCompiling.set(false)
        this.rdscMessage.set('RDSC packet is being compiled. It will appear in Documents shortly.')
      },
      error: () => {
        this.rdscCompiling.set(false)
        this.rdscMessage.set('The packet could not be compiled. Check the checkpoints above.')
      },
    })
  }

  selectSection(k: string): void {
    this.section.set(k)
    const first = this.subNav[k]?.[0]?.k
    if (first) {
      this.sub.set(first)
    }
    if (k === 'disputes') {
      this.loadRdscReadiness()
    }
  }

  selectSub(k: string): void {
    this.sub.set(k)
  }

  is(section: string, sub?: string): boolean {
    return this.section() === section && (sub === undefined || this.sub() === sub)
  }
}
