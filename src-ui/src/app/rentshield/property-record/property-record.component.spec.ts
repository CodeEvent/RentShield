import { TestBed } from '@angular/core/testing'
import { ActivatedRoute, Router } from '@angular/router'
import { allIcons, NgxBootstrapIconsModule } from 'ngx-bootstrap-icons'
import { of, throwError } from 'rxjs'
import { PropertyRecordComponent } from './property-record.component'
import {
  Notice,
  RdscReadiness,
  RentshieldApiService,
} from '../services/rentshield-api.service'
import { PropertyWorkspaceService } from '../services/property-workspace.service'

/**
 * The RDSC compliance gate must be enforced in the client too: the Compile
 * action is a no-op unless the server-returned can_compile is true. (The
 * server re-checks the same gate; this is UX, not the security boundary.)
 */
describe('PropertyRecordComponent — RDSC compliance gate', () => {
  let component: PropertyRecordComponent
  let api: jest.Mocked<Partial<RentshieldApiService>>

  const servedNotice = { id: 7, unit_no: '1204', served_date: '2026-09-01' } as Notice

  const readiness = (can: boolean): RdscReadiness => ({
    identity: can,
    lease: can,
    delivery: can,
    can_compile: can,
    checkpoints: [
      { key: 'identity', label: 'Owner identity verified', ok: can, detail: '' },
      { key: 'lease', label: 'Registered Ejari linked', ok: can, detail: '' },
      { key: 'delivery', label: 'Notice served with proof', ok: can, detail: '' },
    ],
  })

  beforeEach(() => {
    api = {
      listNotices: jest.fn().mockReturnValue(of([])),
      getRdscReadiness: jest.fn().mockReturnValue(of(readiness(false))),
      generateRdscPacket: jest.fn().mockReturnValue(of({ task_id: 't1' })),
    }
    const workspace: Partial<PropertyWorkspaceService> = {
      getInspections: jest.fn().mockReturnValue(of([])),
      getMaintenance: jest.fn().mockReturnValue(of([])),
      getMessages: jest.fn().mockReturnValue(of([])),
    }

    TestBed.configureTestingModule({
      imports: [PropertyRecordComponent, NgxBootstrapIconsModule.pick(allIcons)],
      providers: [
        { provide: RentshieldApiService, useValue: api },
        { provide: PropertyWorkspaceService, useValue: workspace },
        { provide: Router, useValue: { navigate: jest.fn() } },
        { provide: ActivatedRoute, useValue: { snapshot: { paramMap: { get: () => null } } } },
      ],
    })
    const fixture = TestBed.createComponent(PropertyRecordComponent)
    component = fixture.componentInstance
    component.allNotices.set([servedNotice])
  })

  it('loadRdscReadiness stores the server payload', () => {
    api.getRdscReadiness!.mockReturnValue(of(readiness(true)))
    component.loadRdscReadiness()
    expect(api.getRdscReadiness).toHaveBeenCalledWith(7)
    expect(component.rdscReadiness()?.can_compile).toBe(true)
  })

  it('does NOT compile when can_compile is false', () => {
    component.rdscReadiness.set(readiness(false))
    component.compileRdscPacket()
    expect(api.generateRdscPacket).not.toHaveBeenCalled()
  })

  it('does NOT compile when readiness has not loaded', () => {
    component.rdscReadiness.set(null)
    component.compileRdscPacket()
    expect(api.generateRdscPacket).not.toHaveBeenCalled()
  })

  it('compiles when all checkpoints pass', () => {
    component.rdscReadiness.set(readiness(true))
    component.compileRdscPacket()
    expect(api.generateRdscPacket).toHaveBeenCalledWith(7)
  })

  it('surfaces an error message when compile fails server-side', () => {
    component.rdscReadiness.set(readiness(true))
    api.generateRdscPacket!.mockReturnValue(throwError(() => new Error('400')))
    component.compileRdscPacket()
    expect(component.rdscMessage()).toContain('could not be compiled')
  })

  it('selecting the Disputes tab triggers a readiness load', () => {
    component.selectSection('disputes')
    expect(api.getRdscReadiness).toHaveBeenCalledWith(7)
  })
})
