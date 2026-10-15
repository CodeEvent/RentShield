import { Injectable } from '@angular/core'
import { Observable, of } from 'rxjs'

export interface Reminder {
  id: number
  title: string
  due: string
  kind: 'contract' | 'notice' | 'inspection' | 'payment'
  urgent: boolean
}
export interface Inspection {
  id: number
  date: string
  type: string
  result: string
  resultClass: string
}
export interface MaintenanceItem {
  id: number
  summary: string
  reportedBy: string
  status: string
  statusClass: string
  date: string
}
export interface Message {
  id: number
  from: string
  preview: string
  when: string
  unread: boolean
}

/**
 * Backs the newer property tabs (Reminders, Inspections, Maintenance,
 * Messages). Returns mock data today so the UI and architecture are in place;
 * each getter is a drop-in point for a real endpoint later (scoped by
 * propertyId).
 */
@Injectable({ providedIn: 'root' })
export class PropertyWorkspaceService {
  getReminders(_propertyId: string): Observable<Reminder[]> {
    return of([
      { id: 1, title: 'Tenancy contract ends', due: '15 Sep 2025', kind: 'contract', urgent: true },
      { id: 2, title: 'Notice window opens', due: 'in 42 days', kind: 'notice', urgent: true },
      { id: 3, title: 'Annual inspection due', due: '01 Dec 2025', kind: 'inspection', urgent: false },
    ])
  }

  getInspections(_propertyId: string): Observable<Inspection[]> {
    return of([
      { id: 1, date: '01 Dec 2024', type: 'Annual', result: 'Passed', resultClass: 'ok' },
      { id: 2, date: '14 Jun 2024', type: 'Move-in', result: 'Minor issues', resultClass: 'warn' },
    ])
  }

  getMaintenance(_propertyId: string): Observable<MaintenanceItem[]> {
    return of([
      {
        id: 1,
        summary: 'AC not cooling in the master bedroom',
        reportedBy: 'Tenant',
        status: 'In progress',
        statusClass: 'warn',
        date: '02 Oct',
      },
      {
        id: 2,
        summary: 'Kitchen tap leak',
        reportedBy: 'Tenant',
        status: 'Resolved',
        statusClass: 'ok',
        date: '18 Sep',
      },
    ])
  }

  getMessages(_propertyId: string): Observable<Message[]> {
    return of([
      { id: 1, from: 'John M. Smith (tenant)', preview: 'About the renewal of my contract…', when: '2h ago', unread: true },
      { id: 2, from: 'Notary Public', preview: 'Your verification was approved.', when: '09 Oct', unread: false },
    ])
  }
}
