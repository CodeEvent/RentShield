import { CommonModule } from '@angular/common'
import { Component, inject, Input, OnInit } from '@angular/core'
import { FormBuilder, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms'
import { NgbActiveModal } from '@ng-bootstrap/ng-bootstrap'

// Collects the two fields RDSCFilingFlow.record_filing needs (see
// rentshield_workflow/flows.py) and hands them back via activeModal.close()
// -- the actual POST to rdsc-filing-task/complete/ happens in
// notices-list.component.ts, same split as every other dialog in this app
// (e.g. ConfirmDialogComponent): the dialog collects input, the caller acts.
@Component({
  selector: 'app-record-rdc-filing-dialog',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule],
  templateUrl: './record-rdc-filing-dialog.component.html',
})
export class RecordRdcFilingDialogComponent implements OnInit {
  activeModal = inject(NgbActiveModal)
  private fb = inject(FormBuilder)

  @Input() existingCaseReference: string | null = null
  @Input() existingFiledDate: string | null = null

  form: FormGroup = this.fb.group({
    rdc_case_reference: ['', Validators.required],
    filed_date: ['', Validators.required],
  })

  ngOnInit(): void {
    if (this.existingCaseReference || this.existingFiledDate) {
      this.form.patchValue({
        rdc_case_reference: this.existingCaseReference ?? '',
        filed_date: this.existingFiledDate ?? '',
      })
    }
  }

  submit(): void {
    if (this.form.invalid) return
    this.activeModal.close(this.form.value)
  }
}
